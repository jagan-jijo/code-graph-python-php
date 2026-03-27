from __future__ import annotations
import asyncio
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect

from graph import create_store
from graph.store import BaseGraphStore
from indexer.pipeline import IndexingCancelled, run_indexing
from models.project import IndexRequest, ProgressEvent, Project, ProjectSourceType, ProjectStatus
from source_resolver import resolve_source_path

router = APIRouter(prefix="/api/projects", tags=["projects"])

_projects: dict[str, Project] = {}
_stores: dict[str, BaseGraphStore] = {}
_listeners: dict[str, set[WebSocket]] = defaultdict(set)
_cancel_events: dict[str, asyncio.Event] = {}


def get_project(project_id: str) -> Project:
    project = _projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_store(project_id: str) -> BaseGraphStore:
    store = _stores.get(project_id)
    if not store:
        raise HTTPException(status_code=404, detail="Project graph not found")
    return store


async def _broadcast(project_id: str, event: ProgressEvent) -> None:
    listeners = list(_listeners.get(project_id, set()))
    stale: list[WebSocket] = []
    for ws in listeners:
        try:
            await ws.send_json(event.model_dump())
        except Exception:
            stale.append(ws)
    for ws in stale:
        _listeners[project_id].discard(ws)


async def _index_project(project: Project) -> None:
    store = _stores.setdefault(project.id, create_store(project.config.graph_backend.value, project.id))
    cancel_event = _cancel_events.setdefault(project.id, asyncio.Event())
    cancel_event.clear()
    project.status = ProjectStatus.INDEXING
    project.error_message = None

    async def on_progress(event: ProgressEvent) -> None:
        if event.error:
            project.status = ProjectStatus.ERROR
            project.error_message = event.error
        await _broadcast(project.id, event)

    try:
        await on_progress(
            ProgressEvent(
                project_id=project.id,
                stage="source",
                message="Resolving source repository…",
                progress=0.02,
            )
        )
        resolved_path, source_type, source_url = await asyncio.to_thread(resolve_source_path, project.source_url or project.path)
        project.source_type = ProjectSourceType(source_type)
        project.source_url = source_url
        project.resolved_path = str(resolved_path)

        stats = await run_indexing(
            project.id,
            str(resolved_path),
            project.language,
            project.config,
            store,
            on_progress=on_progress,
            should_cancel=cancel_event.is_set,
        )
        if cancel_event.is_set():
            project.status = ProjectStatus.CANCELLED
            project.error_message = None
            await _broadcast(
                project.id,
                ProgressEvent(project_id=project.id, stage="cancelled", message="Analysis stopped.", progress=0.0),
            )
            return
        project.file_count = stats["file_count"]
        project.node_count = stats["node_count"]
        project.edge_count = stats["edge_count"]
        project.last_indexed = datetime.utcnow().isoformat()
        project.status = ProjectStatus.READY
        project.error_message = None
        await _broadcast(
            project.id,
            ProgressEvent(project_id=project.id, stage="ready", message="Project ready", progress=1.0),
        )
    except IndexingCancelled:
        project.status = ProjectStatus.CANCELLED
        project.error_message = None
        await _broadcast(
            project.id,
            ProgressEvent(project_id=project.id, stage="cancelled", message="Analysis stopped.", progress=0.0),
        )
    except Exception as exc:
        project.status = ProjectStatus.ERROR
        project.error_message = str(exc)
        await _broadcast(
            project.id,
            ProgressEvent(
                project_id=project.id,
                stage="error",
                message="Indexing failed",
                progress=1.0,
                error=str(exc),
            ),
        )
    finally:
        _cancel_events.pop(project.id, None)


@router.post("/index", response_model=Project)
async def index_project(request: IndexRequest, background_tasks: BackgroundTasks) -> Project:
    project = Project(name=request.name, path=request.path, language=request.language, config=request.config)
    _projects[project.id] = project
    _stores[project.id] = create_store(project.config.graph_backend.value, project.id)
    background_tasks.add_task(_index_project, project)
    return project


@router.get("/{project_id}/status", response_model=Project)
async def get_project_status(project_id: str) -> Project:
    return get_project(project_id)


@router.get("/{project_id}/overview")
async def get_project_overview(project_id: str) -> dict:
    project = get_project(project_id)
    store = get_store(project_id)
    return {
        "project": project.model_dump(),
        "stats": store.get_stats().model_dump(),
    }


@router.post("/{project_id}/reindex", response_model=Project)
async def reindex_project(project_id: str, background_tasks: BackgroundTasks) -> Project:
    project = get_project(project_id)
    background_tasks.add_task(_index_project, project)
    return project


@router.post("/{project_id}/cancel", response_model=Project)
async def cancel_project(project_id: str) -> Project:
    project = get_project(project_id)
    if project.status != ProjectStatus.INDEXING:
        raise HTTPException(status_code=400, detail="Project is not currently indexing")

    cancel_event = _cancel_events.setdefault(project_id, asyncio.Event())
    cancel_event.set()
    project.status = ProjectStatus.CANCELLED
    project.error_message = None
    await _broadcast(
        project.id,
        ProgressEvent(project_id=project.id, stage="cancelling", message="Stopping analysis…", progress=0.0),
    )
    return project


@router.websocket("/ws/{project_id}")
async def project_progress_ws(websocket: WebSocket, project_id: str) -> None:
    await websocket.accept()
    _listeners[project_id].add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _listeners[project_id].discard(websocket)
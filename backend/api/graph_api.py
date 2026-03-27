from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ai import create_adapter
from api.projects import get_project, get_store
from models.graph import EdgeType, GraphEdge, GraphNode, ProvenanceTag
from models.project import ConstructionMode

router = APIRouter(prefix="/api/projects", tags=["graph"])


def _edge_types(values: list[str] | None) -> list[EdgeType] | None:
    if not values:
        return None
    parsed: list[EdgeType] = []
    for value in values:
        try:
            parsed.append(EdgeType(value))
        except ValueError:
            continue
    return parsed or None


def _provenances(values: list[str] | None) -> list[ProvenanceTag] | None:
    if not values:
        return None
    parsed: list[ProvenanceTag] = []
    for value in values:
        try:
            parsed.append(ProvenanceTag(value))
        except ValueError:
            continue
    return parsed or None


@router.get("/{project_id}/graph")
async def get_graph(
    project_id: str,
    q: str | None = None,
    min_confidence: float = 0.0,
    edge_types: list[str] | None = Query(default=None),
    provenances: list[str] | None = Query(default=None),
) -> dict:
    store = get_store(project_id)
    nodes = store.get_all_nodes()
    edges = store.get_all_edges(
        types=_edge_types(edge_types),
        min_confidence=min_confidence,
        include_provenances=_provenances(provenances),
    )
    if q:
        q_lower = q.lower()
        matched_node_ids = {
            node.id for node in nodes
            if q_lower in node.label.lower()
            or q_lower in (node.qualified_name or "").lower()
            or q_lower in (node.file_path or "").lower()
            or q_lower in str(node.properties.get("relative_path", "")).lower()
            or q_lower in str(node.properties.get("module_name", "")).lower()
        }
        edges = [edge for edge in edges if edge.source_id in matched_node_ids or edge.target_id in matched_node_ids]
        visible_node_ids = set(matched_node_ids)
        for edge in edges:
            visible_node_ids.add(edge.source_id)
            visible_node_ids.add(edge.target_id)
        nodes = [node for node in nodes if node.id in visible_node_ids]
    return {
        "nodes": [node.model_dump() for node in nodes],
        "edges": [edge.model_dump() for edge in edges],
        "stats": store.get_stats().model_dump(),
    }


@router.get("/{project_id}/node/{node_id}")
async def get_node(project_id: str, node_id: str) -> dict:
    store = get_store(project_id)
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return {
        "node": node.model_dump(),
        "incoming": [edge.model_dump() for edge in store.get_edges_to(node_id)],
        "outgoing": [edge.model_dump() for edge in store.get_edges_from(node_id)],
    }


@router.get("/{project_id}/node/{node_id}/callers")
async def get_callers(project_id: str, node_id: str) -> list[dict]:
    store = get_store(project_id)
    return [edge.model_dump() for edge in store.get_edges_to(node_id, [EdgeType.CALLS, EdgeType.POSSIBLE_CALLS])]


@router.get("/{project_id}/node/{node_id}/callees")
async def get_callees(project_id: str, node_id: str) -> list[dict]:
    store = get_store(project_id)
    return [edge.model_dump() for edge in store.get_edges_from(node_id, [EdgeType.CALLS, EdgeType.POSSIBLE_CALLS])]


@router.get("/{project_id}/node/{node_id}/references")
async def get_references(project_id: str, node_id: str) -> list[dict]:
    store = get_store(project_id)
    refs = store.get_edges_from(node_id, [EdgeType.REFERENCES, EdgeType.POSSIBLE_REFERENCES])
    refs.extend(store.get_edges_to(node_id, [EdgeType.REFERENCES, EdgeType.POSSIBLE_REFERENCES]))
    return [edge.model_dump() for edge in refs]


@router.get("/{project_id}/path")
async def get_shortest_path(project_id: str, from_id: str = Query(alias="from"), to_id: str = Query(alias="to")) -> dict:
    store = get_store(project_id)
    path = store.shortest_path(from_id, to_id)
    nodes = [store.get_node(node_id).model_dump() for node_id in path if store.get_node(node_id)]
    return {"path": path, "nodes": nodes}


@router.get("/{project_id}/source-snippet")
async def get_source_snippet(project_id: str, file_path: str, line_start: int = 1, line_end: int = 40) -> dict:
    project = get_project(project_id)
    target = Path(file_path)
    root = Path(project.path).resolve()
    try:
        resolved = target.resolve()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if root not in resolved.parents and resolved != root:
        raise HTTPException(status_code=400, detail="Requested file is outside project root")
    try:
        lines = resolved.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    start_index = max(line_start - 1, 0)
    end_index = min(line_end, len(lines))
    snippet = "\n".join(lines[start_index:end_index])
    return {"file_path": str(resolved), "line_start": line_start, "line_end": end_index, "snippet": snippet}


@router.post("/{project_id}/query")
async def query_graph(project_id: str, payload: dict) -> dict:
    store = get_store(project_id)
    query = str(payload.get("query", "")).strip()
    if not query:
        return {"nodes": [], "edges": []}
    nodes = store.find_nodes_by_name(query, limit=50)
    node_ids = {node.id for node in nodes}
    edges = [edge for edge in store.get_all_edges() if edge.source_id in node_ids or edge.target_id in node_ids]
    return {
        "nodes": [node.model_dump() for node in nodes],
        "edges": [edge.model_dump() for edge in edges],
    }


@router.post("/{project_id}/refine-graph")
async def refine_graph(project_id: str) -> dict:
    project = get_project(project_id)
    store = get_store(project_id)
    if project.config.construction_mode != ConstructionMode.NATIVE_PLUS_MODEL_REFINEMENT:
        raise HTTPException(status_code=400, detail="Model-assisted refinement is disabled for this project")
    if not project.config.model_config_data:
        raise HTTPException(status_code=400, detail="Model configuration is missing")

    adapter = create_adapter(project.config.model_config_data)
    model_name = (
        project.config.model_config_data.code_model
        or project.config.model_config_data.query_model
        or project.config.model_config_data.planner_model
    )
    if not model_name:
        raise HTTPException(status_code=400, detail="No model name configured")

    store.clear_model_inferences()

    summarized = 0
    for node in store.get_all_nodes()[:25]:
        if node.ai_summary:
            continue
        summary = await adapter.summarize_symbol(
            {
                "type": node.type.value,
                "name": node.label,
                "signature": node.signature,
                "docstring": node.docstring,
            },
            model_name,
        )
        node.ai_summary = summary
        node.provenance = node.provenance
        store.upsert_node(node)
        summarized += 1

    unresolved_edges = store.get_all_edges(types=[EdgeType.POSSIBLE_CALLS])[:10]
    proposals: list[dict] = []
    for edge in unresolved_edges:
        source = store.get_node(edge.source_id)
        target = store.get_node(edge.target_id)
        if not source or not target:
            continue

        candidates = [
            node for node in store.find_nodes_by_name(target.label, limit=8)
            if node.id != target.id and not node.id.startswith("unresolved:")
        ]
        if not candidates:
            continue

        schema = {
            "target_ids": ["string"],
            "confidence": 0.0,
            "reasoning": "string",
        }
        candidate_block = "\n".join(
            f"- {candidate.id}: {candidate.qualified_name or candidate.label} ({candidate.file_path or 'unknown file'})"
            for candidate in candidates
        )
        extracted = await adapter.structured_extract(
            (
                f"Source symbol: {source.qualified_name or source.label}\n"
                f"Unresolved callee label: {target.label}\n"
                f"Original evidence: {edge.evidence or 'none'}\n"
                f"Choose zero or more likely targets from this list:\n{candidate_block}\n"
                "Return only target_ids that are plausible call targets."
            ),
            schema,
            model_name,
        )
        selected_ids = extracted.get("target_ids", []) if isinstance(extracted, dict) else []
        confidence = float(extracted.get("confidence", 0.45)) if isinstance(extracted, dict) else 0.45
        reasoning = str(extracted.get("reasoning", edge.evidence or "model refinement")) if isinstance(extracted, dict) else (edge.evidence or "model refinement")

        for target_id in selected_ids:
            candidate = store.get_node(target_id)
            if not candidate:
                continue
            model_edge = GraphEdge(
                id=f"MODEL_ASSISTED_INFERENCE:{edge.id}:{target_id}",
                type=EdgeType.POSSIBLE_CALLS,
                source_id=edge.source_id,
                target_id=target_id,
                language=edge.language,
                confidence=max(0.0, min(confidence, 1.0)),
                evidence=reasoning,
                file_path=source.file_path,
                line_number=edge.line_number,
                provenance=ProvenanceTag.MODEL_ASSISTED_INFERENCE,
                provenance_detail=edge.id,
                model_name=model_name,
                properties={"refined_from": edge.id, "layer": "model_inference"},
            )
            store.upsert_edge(model_edge)
            proposals.append(
                {
                    "edge_id": model_edge.id,
                    "from": source.label,
                    "to": candidate.label,
                    "confidence": model_edge.confidence,
                    "provenance": model_edge.provenance.value,
                }
            )

    return {"summaries_added": summarized, "proposals": proposals}
from __future__ import annotations
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from source_resolver import resolve_source_path

router = APIRouter(prefix="/api", tags=["browse"])

_EXTENSIONS = {
    "python": {".py"},
    "php": {".php"},
    "mixed": {".py", ".php"},
}


@router.get("/browse")
async def browse_files(
    path: str = Query(...),
    language: str = Query("python"),
    limit: int = Query(400, ge=50, le=2000),
) -> dict:
    try:
        resolved_root, source_type, source_url = await asyncio.to_thread(resolve_source_path, path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    root = Path(resolved_root)
    extensions = _EXTENSIONS.get(language, _EXTENSIONS["mixed"])
    files = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in extensions:
            continue
        relative = file_path.relative_to(root).as_posix()
        files.append({
            "path": str(file_path),
            "relative_path": relative,
            "name": file_path.name,
        })
        if len(files) >= limit:
            break
    return {
        "root": str(root),
        "files": files,
        "limit": limit,
        "source_type": source_type,
        "source_url": source_url,
    }
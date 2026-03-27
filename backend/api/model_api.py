from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai import create_adapter
from models.project import ModelConfig

router = APIRouter(prefix="/api/model", tags=["model"])


class ModelConnectionRequest(BaseModel):
    config: ModelConfig


@router.post("/test-connection")
async def test_connection(request: ModelConnectionRequest) -> dict:
    adapter = create_adapter(request.config)
    healthy = await adapter.health_check()
    return {"ok": healthy}


@router.post("/list-models")
async def list_models(request: ModelConnectionRequest) -> dict:
    adapter = create_adapter(request.config)
    if not await adapter.health_check():
        raise HTTPException(status_code=400, detail="Model endpoint is not reachable")
    return {"models": await adapter.list_models()}
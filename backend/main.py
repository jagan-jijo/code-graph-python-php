from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.browse_api import router as browse_router
from api.graph_api import router as graph_router
from api.model_api import router as model_router
from api.projects import router as projects_router

app = FastAPI(title="Code Graph Builder", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


app.include_router(projects_router)
app.include_router(graph_router)
app.include_router(model_router)
app.include_router(browse_router)
from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel
import uuid
from datetime import datetime
from config import (
    OLLAMA_API_KEY,
    OLLAMA_BASE_URL,
    OPENAI_COMPATIBLE_API_KEY,
    OPENAI_COMPATIBLE_BASE_URL,
    OPENWEBUI_API_KEY,
    OPENWEBUI_BASE_URL,
)


class AnalysisDepth(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"


class GraphBackend(str, Enum):
    IN_MEMORY = "in_memory"
    SQLITE = "sqlite"
    MEMGRAPH = "memgraph"
    FALKORDB = "falkordb"
    NEO4J = "neo4j"


class ConstructionMode(str, Enum):
    NATIVE_ONLY = "native_only"
    NATIVE_PLUS_MODEL_REFINEMENT = "native_plus_model_refinement"


class ModelProviderType(str, Enum):
    OLLAMA_NATIVE = "ollama_native_api"
    OPENWEBUI = "openwebui_api"
    OPENAI_COMPATIBLE = "openai_compatible_api"


class RemoteSendPolicy(str, Enum):
    GRAPH_METADATA_ONLY = "graph_metadata_only"
    GRAPH_METADATA_PLUS_SNIPPETS = "graph_metadata_plus_selected_snippets"
    FULL_SELECTED_FILE_ON_DEMAND = "full_selected_file_context_only_on_demand"


class ModelConfig(BaseModel):
    provider_type: ModelProviderType = ModelProviderType.OLLAMA_NATIVE
    base_url: str = OLLAMA_BASE_URL
    api_key: Optional[str] = OLLAMA_API_KEY or None
    remote_send_policy: RemoteSendPolicy = RemoteSendPolicy.GRAPH_METADATA_PLUS_SNIPPETS
    planner_model: Optional[str] = None
    code_model: Optional[str] = None
    query_model: Optional[str] = None


def build_default_model_config(provider_type: ModelProviderType) -> ModelConfig:
    if provider_type == ModelProviderType.OPENWEBUI:
        return ModelConfig(
            provider_type=provider_type,
            base_url=OPENWEBUI_BASE_URL,
            api_key=OPENWEBUI_API_KEY or None,
        )
    if provider_type == ModelProviderType.OPENAI_COMPATIBLE:
        return ModelConfig(
            provider_type=provider_type,
            base_url=OPENAI_COMPATIBLE_BASE_URL,
            api_key=OPENAI_COMPATIBLE_API_KEY or None,
        )
    return ModelConfig(
        provider_type=provider_type,
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY or None,
    )


class ProjectConfig(BaseModel):
    entry_points: list[str] = []
    focus_modules: list[str] = []
    exclude_patterns: list[str] = []
    analysis_depth: AnalysisDepth = AnalysisDepth.BALANCED
    graph_backend: GraphBackend = GraphBackend.SQLITE
    construction_mode: ConstructionMode = ConstructionMode.NATIVE_ONLY
    model_config_data: Optional[ModelConfig] = None


class ProjectStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"
    REFINING = "refining"
    CANCELLED = "cancelled"


class ProjectSourceType(str, Enum):
    LOCAL_PATH = "local_path"
    GITHUB_URL = "github_url"


class Project(BaseModel):
    id: str = ""
    name: str
    path: str
    language: str = "python"
    source_type: ProjectSourceType = ProjectSourceType.LOCAL_PATH
    source_url: Optional[str] = None
    resolved_path: Optional[str] = None
    status: ProjectStatus = ProjectStatus.PENDING
    config: ProjectConfig = ProjectConfig()
    created_at: str = ""
    last_indexed: Optional[str] = None
    error_message: Optional[str] = None
    file_count: int = 0
    node_count: int = 0
    edge_count: int = 0

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()


class IndexRequest(BaseModel):
    name: str
    path: str
    language: str = "python"
    config: ProjectConfig = ProjectConfig()


class ProgressEvent(BaseModel):
    project_id: str
    stage: str
    message: str
    progress: float = 0.0
    files_processed: int = 0
    files_total: int = 0
    error: Optional[str] = None

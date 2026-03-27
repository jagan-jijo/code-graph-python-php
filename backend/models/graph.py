from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel


class NodeType(str, Enum):
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"
    MODULE = "module"
    NAMESPACE = "namespace"
    CLASS = "class"
    INTERFACE = "interface"
    TRAIT = "trait"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"


class EdgeType(str, Enum):
    CONTAINS = "CONTAINS"
    DEFINED_IN = "DEFINED_IN"
    IMPORTS = "IMPORTS"
    USES_MODULE = "USES_MODULE"
    CALLS = "CALLS"
    REFERENCES = "REFERENCES"
    EXTENDS = "EXTENDS"
    IMPLEMENTS = "IMPLEMENTS"
    USES_TRAIT = "USES_TRAIT"
    OVERRIDES = "OVERRIDES"
    DEPENDS_ON = "DEPENDS_ON"
    POSSIBLE_CALLS = "POSSIBLE_CALLS"
    POSSIBLE_REFERENCES = "POSSIBLE_REFERENCES"


class ProvenanceTag(str, Enum):
    PARSER_FACT = "parser_fact"
    REFERENCE_INDEX_FACT = "reference_index_fact"
    GRAPH_ALGORITHM_INFERENCE = "graph_algorithm_inference"
    MODEL_ASSISTED_INFERENCE = "model_assisted_inference"


class Language(str, Enum):
    PYTHON = "python"
    PHP = "php"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class GraphNode(BaseModel):
    id: str
    type: NodeType
    label: str
    language: Language = Language.UNKNOWN
    provenance: ProvenanceTag = ProvenanceTag.PARSER_FACT
    confidence: float = 1.0
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    qualified_name: Optional[str] = None
    docstring: Optional[str] = None
    signature: Optional[str] = None
    decorators: list[str] = []
    is_async: bool = False
    is_entry_point: bool = False
    hotspot_score: float = 0.0
    ai_summary: Optional[str] = None
    properties: dict[str, Any] = {}


class GraphEdge(BaseModel):
    id: str
    type: EdgeType
    source_id: str
    target_id: str
    language: Language = Language.UNKNOWN
    confidence: float = 1.0
    evidence: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    provenance: ProvenanceTag = ProvenanceTag.PARSER_FACT
    provenance_detail: Optional[str] = None
    model_name: Optional[str] = None
    properties: dict[str, Any] = {}


class GraphStats(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    file_count: int = 0
    class_count: int = 0
    function_count: int = 0
    method_count: int = 0
    unresolved_calls: int = 0
    model_inferred_edges: int = 0

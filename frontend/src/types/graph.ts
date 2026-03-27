export type NodeType =
  | 'repository'
  | 'directory'
  | 'file'
  | 'module'
  | 'namespace'
  | 'class'
  | 'interface'
  | 'trait'
  | 'enum'
  | 'function'
  | 'method';

export type EdgeType =
  | 'CONTAINS'
  | 'DEFINED_IN'
  | 'IMPORTS'
  | 'USES_MODULE'
  | 'CALLS'
  | 'REFERENCES'
  | 'EXTENDS'
  | 'IMPLEMENTS'
  | 'USES_TRAIT'
  | 'OVERRIDES'
  | 'DEPENDS_ON'
  | 'POSSIBLE_CALLS'
  | 'POSSIBLE_REFERENCES';

export type ProvenanceTag =
  | 'parser_fact'
  | 'reference_index_fact'
  | 'graph_algorithm_inference'
  | 'model_assisted_inference';

export type ExternalKind = 'builtin' | 'stdlib' | 'third_party' | 'unknown';

export interface GraphNodeProperties {
  relative_path?: string;
  module_name?: string;
  external_kind?: ExternalKind;
  dependency_manifest?: string;
  dependency_name?: string;
  dependency_version?: string | null;
  ecosystem?: string;
  [key: string]: unknown;
}

export interface GraphEdgeProperties {
  refined_from?: string;
  layer?: string;
  [key: string]: unknown;
}

export interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  language: string;
  provenance: ProvenanceTag;
  confidence: number;
  file_path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  qualified_name?: string | null;
  docstring?: string | null;
  signature?: string | null;
  decorators?: string[];
  is_async?: boolean;
  is_entry_point?: boolean;
  hotspot_score?: number;
  ai_summary?: string | null;
  properties?: GraphNodeProperties;
}

export interface GraphEdge {
  id: string;
  type: EdgeType;
  source_id: string;
  target_id: string;
  language: string;
  confidence: number;
  evidence?: string | null;
  file_path?: string | null;
  line_number?: number | null;
  provenance: ProvenanceTag;
  provenance_detail?: string | null;
  model_name?: string | null;
  properties?: GraphEdgeProperties;
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
  file_count: number;
  class_count: number;
  function_count: number;
  method_count: number;
  unresolved_calls: number;
  model_inferred_edges: number;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

export interface GraphFilters {
  minConfidence: number;
  q: string;
  includeParserFacts: boolean;
  includeReferenceFacts: boolean;
  includeGraphInference: boolean;
  includeModelInference: boolean;
  hideNativeLibraryNodes: boolean;
  hideThirdPartyDependencyNodes: boolean;
  showProvenanceBadges: boolean;
  groupByModules: boolean;
}
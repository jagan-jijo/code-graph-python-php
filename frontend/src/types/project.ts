export type AnalysisDepth = 'fast' | 'balanced' | 'deep';
export type GraphBackend = 'sqlite' | 'in_memory' | 'memgraph' | 'falkordb' | 'neo4j';
export type ConstructionMode = 'native_only' | 'native_plus_model_refinement';
export type ProviderType = 'ollama_native_api' | 'openwebui_api' | 'openai_compatible_api';
export type AnalysisProvider = 'native' | 'ollama' | 'openwebui';
export type RemoteSendPolicy =
  | 'graph_metadata_only'
  | 'graph_metadata_plus_selected_snippets'
  | 'full_selected_file_context_only_on_demand';

export interface ModelConfig {
  provider_type: ProviderType;
  base_url: string;
  api_key?: string | null;
  remote_send_policy: RemoteSendPolicy;
  planner_model?: string | null;
  code_model?: string | null;
  query_model?: string | null;
}

export interface ProjectConfig {
  entry_points: string[];
  focus_modules: string[];
  exclude_patterns: string[];
  analysis_depth: AnalysisDepth;
  graph_backend: GraphBackend;
  construction_mode: ConstructionMode;
  model_config_data?: ModelConfig | null;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  language: string;
  source_type?: 'local_path' | 'github_url';
  source_url?: string | null;
  resolved_path?: string | null;
  status: 'pending' | 'indexing' | 'ready' | 'error' | 'refining' | 'cancelled';
  config: ProjectConfig;
  created_at: string;
  last_indexed?: string | null;
  error_message?: string | null;
  file_count: number;
  node_count: number;
  edge_count: number;
}

export interface IndexRequest {
  name: string;
  path: string;
  language: string;
  config: ProjectConfig;
}

export interface ProgressEvent {
  project_id: string;
  stage: string;
  message: string;
  progress: number;
  files_processed: number;
  files_total: number;
  error?: string | null;
}

export interface BrowseFile {
  path: string;
  relative_path: string;
  name: string;
}
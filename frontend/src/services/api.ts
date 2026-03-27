import type { BrowseFile, IndexRequest, ModelConfig, Project, ProgressEvent } from '../types/project';
import type { GraphResponse, GraphNode } from '../types/graph';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function createProject(payload: IndexRequest): Promise<Project> {
  return request<Project>('/api/projects/index', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getProjectStatus(projectId: string): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}/status`);
}

export async function cancelProject(projectId: string): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}/cancel`, {
    method: 'POST',
  });
}

export async function getProjectOverview(projectId: string): Promise<unknown> {
  return request(`/api/projects/${projectId}/overview`);
}

export async function getGraph(projectId: string, params: URLSearchParams): Promise<GraphResponse> {
  return request<GraphResponse>(`/api/projects/${projectId}/graph?${params.toString()}`);
}

export async function getNode(projectId: string, nodeId: string): Promise<{ node: GraphNode }> {
  return request(`/api/projects/${projectId}/node/${encodeURIComponent(nodeId)}`);
}

export async function queryGraph(projectId: string, query: string): Promise<GraphResponse> {
  return request(`/api/projects/${projectId}/query`, {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}

export async function refineGraph(projectId: string): Promise<unknown> {
  return request(`/api/projects/${projectId}/refine-graph`, { method: 'POST' });
}

export async function testModelConnection(config: ModelConfig): Promise<{ ok: boolean }> {
  return request('/api/model/test-connection', {
    method: 'POST',
    body: JSON.stringify({ config }),
  });
}

export async function listModels(config: ModelConfig): Promise<{ models: string[] }> {
  return request('/api/model/list-models', {
    method: 'POST',
    body: JSON.stringify({ config }),
  });
}

export async function browseFiles(path: string, language: string, limit = 400): Promise<{ root: string; files: BrowseFile[]; limit: number; source_type?: 'local_path' | 'github_url'; source_url?: string | null }> {
  const params = new URLSearchParams({ path, language, limit: String(limit) });
  return request(`/api/browse?${params.toString()}`);
}

export async function getSourceSnippet(projectId: string, filePath: string, lineStart = 1, lineEnd = 40): Promise<{ snippet: string }> {
  const params = new URLSearchParams({ file_path: filePath, line_start: String(lineStart), line_end: String(lineEnd) });
  return request(`/api/projects/${projectId}/source-snippet?${params.toString()}`);
}

export function connectProgress(projectId: string, onEvent: (event: ProgressEvent) => void): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${window.location.host}/api/projects/ws/${projectId}`);
  socket.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as ProgressEvent);
    } catch {
      return;
    }
  };
  return socket;
}
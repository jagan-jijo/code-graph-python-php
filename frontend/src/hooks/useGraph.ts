import { useEffect, useState } from 'react';

import { getGraph } from '../services/api';
import { useAppStore } from '../store/store';
import type { GraphEdge, GraphNode, GraphResponse } from '../types/graph';

function getExternalKind(node: GraphNode): string | null {
  const value = node.properties?.external_kind;
  return typeof value === 'string' ? value : null;
}

function isNativeLibraryNode(node: GraphNode): boolean {
  if (node.file_path) {
    return false;
  }
  const externalKind = getExternalKind(node);
  if (externalKind === 'builtin' || externalKind === 'stdlib') {
    return true;
  }
  return node.id.startsWith('unresolved:') && externalKind !== 'third_party';
}

function isThirdPartyDependencyNode(node: GraphNode): boolean {
  if (node.file_path) {
    return false;
  }
  const externalKind = getExternalKind(node);
  return externalKind === 'third_party';
}

function filterGraphNodes(graph: GraphResponse, predicate: (node: GraphNode) => boolean): GraphResponse {
  const hiddenNodeIds = new Set(graph.nodes.filter(predicate).map((node) => node.id));
  if (hiddenNodeIds.size === 0) {
    return graph;
  }

  const visibleEdges = graph.edges.filter(
    (edge: GraphEdge) => !hiddenNodeIds.has(edge.source_id) && !hiddenNodeIds.has(edge.target_id),
  );
  const connectedNodeIds = new Set<string>();
  visibleEdges.forEach((edge) => {
    connectedNodeIds.add(edge.source_id);
    connectedNodeIds.add(edge.target_id);
  });

  const visibleNodes = graph.nodes.filter(
    (node: GraphNode) => !hiddenNodeIds.has(node.id) && (connectedNodeIds.has(node.id) || Boolean(node.file_path) || node.type === 'repository' || node.type === 'directory' || node.type === 'file' || node.type === 'module'),
  );

  return {
    ...graph,
    nodes: visibleNodes,
    edges: visibleEdges,
    stats: {
      ...graph.stats,
      node_count: visibleNodes.length,
      edge_count: visibleEdges.length,
      unresolved_calls: visibleEdges.filter((edge) => edge.type === 'POSSIBLE_CALLS' || edge.type === 'POSSIBLE_REFERENCES').length,
    },
  };
}

function applyGraphFilters(graph: GraphResponse, hideNativeLibraryNodes: boolean, hideThirdPartyDependencyNodes: boolean): GraphResponse {
  let filteredGraph = graph;
  if (hideNativeLibraryNodes) {
    filteredGraph = filterGraphNodes(filteredGraph, isNativeLibraryNode);
  }
  if (hideThirdPartyDependencyNodes) {
    filteredGraph = filterGraphNodes(filteredGraph, isThirdPartyDependencyNode);
  }
  return filteredGraph;
}

export function useGraph() {
  const { currentProject, filters, graph, setGraph, setError } = useAppStore();
  const [isGraphLoading, setGraphLoading] = useState(false);

  useEffect(() => {
    if (!currentProject || currentProject.status !== 'ready') {
      setGraph(null);
      setGraphLoading(false);
      return;
    }

    let cancelled = false;
    setGraphLoading(true);

    const params = new URLSearchParams();
    if (filters.q.trim()) {
      params.set('q', filters.q.trim());
    }
    params.set('min_confidence', String(filters.minConfidence));

    const provenances: string[] = [];
    if (filters.includeParserFacts) {
      provenances.push('parser_fact');
    }
    if (filters.includeReferenceFacts) {
      provenances.push('reference_index_fact');
    }
    if (filters.includeGraphInference) {
      provenances.push('graph_algorithm_inference');
    }
    if (filters.includeModelInference) {
      provenances.push('model_assisted_inference');
    }
    provenances.forEach((value) => params.append('provenances', value));

    getGraph(currentProject.id, params)
      .then((result) => {
        if (!cancelled) {
          setGraph(applyGraphFilters(result, filters.hideNativeLibraryNodes, filters.hideThirdPartyDependencyNodes));
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setError(error.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setGraphLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [currentProject, filters, setError, setGraph]);

  return { graph, isGraphLoading };
}
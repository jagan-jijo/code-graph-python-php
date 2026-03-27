from __future__ import annotations
from collections import defaultdict
from typing import Optional
import networkx as nx
from .store import BaseGraphStore
from models.graph import GraphNode, GraphEdge, GraphStats, EdgeType, NodeType, ProvenanceTag


class InMemoryGraphStore(BaseGraphStore):
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._out_edges: dict[str, list[str]] = defaultdict(list)
        self._in_edges: dict[str, list[str]] = defaultdict(list)
        self._fingerprints: dict[str, str] = {}
        self._nx: nx.DiGraph = nx.DiGraph()

    def clear(self) -> None:
        self._nodes.clear(); self._edges.clear()
        self._out_edges.clear(); self._in_edges.clear()
        self._fingerprints.clear()
        self._nx.clear()

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node
        self._nx.add_node(node.id)

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.id in self._edges:
            old = self._edges[edge.id]
            if old.id in self._out_edges.get(old.source_id, []):
                self._out_edges[old.source_id].remove(old.id)
            if old.id in self._in_edges.get(old.target_id, []):
                self._in_edges[old.target_id].remove(old.id)
            if self._nx.has_edge(old.source_id, old.target_id):
                self._nx.remove_edge(old.source_id, old.target_id)
        self._edges[edge.id] = edge
        self._out_edges[edge.source_id].append(edge.id)
        self._in_edges[edge.target_id].append(edge.id)
        self._nx.add_edge(edge.source_id, edge.target_id, edge_id=edge.id)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_all_nodes(self, types=None, language=None) -> list[GraphNode]:
        nodes = self._nodes.values()
        if types:
            nodes = (n for n in nodes if n.type in types)  # type: ignore[assignment]
        if language:
            nodes = (n for n in nodes if n.language == language)  # type: ignore[assignment]
        return list(nodes)

    def get_all_edges(self, types=None, min_confidence=0.0, include_provenances=None) -> list[GraphEdge]:
        edges = self._edges.values()
        if types:
            edges = (e for e in edges if e.type in types)  # type: ignore[assignment]
        if min_confidence > 0:
            edges = (e for e in edges if e.confidence >= min_confidence)  # type: ignore[assignment]
        if include_provenances:
            edges = (e for e in edges if e.provenance in include_provenances)  # type: ignore[assignment]
        return list(edges)

    def get_edges_from(self, node_id: str, edge_types=None) -> list[GraphEdge]:
        eids = self._out_edges.get(node_id, [])
        edges = [self._edges[eid] for eid in eids if eid in self._edges]
        if edge_types:
            edges = [e for e in edges if e.type in edge_types]
        return edges

    def get_edges_to(self, node_id: str, edge_types=None) -> list[GraphEdge]:
        eids = self._in_edges.get(node_id, [])
        edges = [self._edges[eid] for eid in eids if eid in self._edges]
        if edge_types:
            edges = [e for e in edges if e.type in edge_types]
        return edges

    def find_nodes_by_name(self, name: str, limit: int = 20) -> list[GraphNode]:
        nl = name.lower()
        return [n for n in self._nodes.values()
                if nl in n.label.lower() or nl in (n.qualified_name or "").lower()][:limit]

    def shortest_path(self, from_id: str, to_id: str) -> list[str]:
        try:
            return nx.shortest_path(self._nx, from_id, to_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_file_fingerprint(self, file_path: str) -> Optional[str]:
        return self._fingerprints.get(file_path)

    def set_file_fingerprint(self, file_path: str, fingerprint: str) -> None:
        self._fingerprints[file_path] = fingerprint

    def get_tracked_files(self) -> dict[str, str]:
        return dict(self._fingerprints)

    def remove_file_records(self, file_path: str) -> None:
        node_ids_to_remove = {
            node.id for node in self._nodes.values()
            if node.file_path == file_path or node.id == f"file:{file_path}"
        }
        edge_ids_to_remove = {
            edge.id for edge in self._edges.values()
            if edge.file_path == file_path or edge.source_id in node_ids_to_remove or edge.target_id in node_ids_to_remove
        }

        for edge_id in edge_ids_to_remove:
            edge = self._edges.pop(edge_id, None)
            if not edge:
                continue
            if edge_id in self._out_edges.get(edge.source_id, []):
                self._out_edges[edge.source_id].remove(edge_id)
            if edge_id in self._in_edges.get(edge.target_id, []):
                self._in_edges[edge.target_id].remove(edge_id)
            if self._nx.has_edge(edge.source_id, edge.target_id):
                self._nx.remove_edge(edge.source_id, edge.target_id)

        for node_id in node_ids_to_remove:
            self._nodes.pop(node_id, None)
            if self._nx.has_node(node_id):
                self._nx.remove_node(node_id)

        self._fingerprints.pop(file_path, None)

    def get_related_files(self, file_path: str) -> set[str]:
        related: set[str] = set()
        node_ids = {
            node.id for node in self._nodes.values()
            if node.file_path == file_path or node.id == f"file:{file_path}"
        }
        for edge in self._edges.values():
            if edge.source_id not in node_ids and edge.target_id not in node_ids and edge.file_path != file_path:
                continue
            for node_id in (edge.source_id, edge.target_id):
                node = self._nodes.get(node_id)
                if node and node.file_path and node.file_path != file_path:
                    related.add(node.file_path)
        return related

    def clear_model_inferences(self) -> None:
        model_edges = [edge.id for edge in self._edges.values() if edge.provenance == ProvenanceTag.MODEL_ASSISTED_INFERENCE]
        for edge_id in model_edges:
            edge = self._edges.pop(edge_id, None)
            if not edge:
                continue
            if edge_id in self._out_edges.get(edge.source_id, []):
                self._out_edges[edge.source_id].remove(edge_id)
            if edge_id in self._in_edges.get(edge.target_id, []):
                self._in_edges[edge.target_id].remove(edge_id)
            if self._nx.has_edge(edge.source_id, edge.target_id):
                self._nx.remove_edge(edge.source_id, edge.target_id)

    def get_stats(self) -> GraphStats:
        s = GraphStats(node_count=len(self._nodes), edge_count=len(self._edges))
        for n in self._nodes.values():
            if n.type == NodeType.FILE: s.file_count += 1
            elif n.type == NodeType.CLASS: s.class_count += 1
            elif n.type == NodeType.FUNCTION: s.function_count += 1
            elif n.type == NodeType.METHOD: s.method_count += 1
        for e in self._edges.values():
            if e.type in (EdgeType.POSSIBLE_CALLS, EdgeType.POSSIBLE_REFERENCES):
                s.unresolved_calls += 1
            if e.provenance == ProvenanceTag.MODEL_ASSISTED_INFERENCE:
                s.model_inferred_edges += 1
        return s

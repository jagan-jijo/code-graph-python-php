from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional

import networkx as nx

from .store import BaseGraphStore
from models.graph import EdgeType, GraphEdge, GraphNode, GraphStats, NodeType, ProvenanceTag


class SQLiteGraphStore(BaseGraphStore):
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._out_edges: dict[str, list[str]] = defaultdict(list)
        self._in_edges: dict[str, list[str]] = defaultdict(list)
        self._fingerprints: dict[str, str] = {}
        self._nx: nx.DiGraph = nx.DiGraph()
        self._init_db()
        self._load()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                file_path TEXT,
                type TEXT NOT NULL,
                label TEXT NOT NULL,
                qualified_name TEXT,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                file_path TEXT,
                type TEXT NOT NULL,
                provenance TEXT NOT NULL,
                confidence REAL NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS file_fingerprints (
                file_path TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def _load(self) -> None:
        for row in self._conn.execute("SELECT payload FROM nodes"):
            node = GraphNode.model_validate_json(row["payload"])
            self._nodes[node.id] = node
            self._nx.add_node(node.id)
        for row in self._conn.execute("SELECT payload FROM edges"):
            edge = GraphEdge.model_validate_json(row["payload"])
            self._edges[edge.id] = edge
            self._out_edges[edge.source_id].append(edge.id)
            self._in_edges[edge.target_id].append(edge.id)
            self._nx.add_edge(edge.source_id, edge.target_id, edge_id=edge.id)
        for row in self._conn.execute("SELECT file_path, fingerprint FROM file_fingerprints"):
            self._fingerprints[row["file_path"]] = row["fingerprint"]

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._out_edges.clear()
        self._in_edges.clear()
        self._fingerprints.clear()
        self._nx.clear()
        self._conn.executescript("DELETE FROM nodes; DELETE FROM edges; DELETE FROM file_fingerprints;")
        self._conn.commit()

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node
        self._nx.add_node(node.id)
        payload = node.model_dump_json()
        self._conn.execute(
            """
            INSERT INTO nodes(id, file_path, type, label, qualified_name, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                file_path=excluded.file_path,
                type=excluded.type,
                label=excluded.label,
                qualified_name=excluded.qualified_name,
                payload=excluded.payload
            """,
            (node.id, node.file_path, node.type.value, node.label, node.qualified_name, payload),
        )
        self._conn.commit()

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.id in self._edges:
            old = self._edges[edge.id]
            if edge.id in self._out_edges.get(old.source_id, []):
                self._out_edges[old.source_id].remove(edge.id)
            if edge.id in self._in_edges.get(old.target_id, []):
                self._in_edges[old.target_id].remove(edge.id)
            if self._nx.has_edge(old.source_id, old.target_id):
                self._nx.remove_edge(old.source_id, old.target_id)
        self._edges[edge.id] = edge
        self._out_edges[edge.source_id].append(edge.id)
        self._in_edges[edge.target_id].append(edge.id)
        self._nx.add_edge(edge.source_id, edge.target_id, edge_id=edge.id)
        payload = edge.model_dump_json()
        self._conn.execute(
            """
            INSERT INTO edges(id, source_id, target_id, file_path, type, provenance, confidence, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                source_id=excluded.source_id,
                target_id=excluded.target_id,
                file_path=excluded.file_path,
                type=excluded.type,
                provenance=excluded.provenance,
                confidence=excluded.confidence,
                payload=excluded.payload
            """,
            (edge.id, edge.source_id, edge.target_id, edge.file_path, edge.type.value, edge.provenance.value, edge.confidence, payload),
        )
        self._conn.commit()

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_all_nodes(self, types=None, language=None) -> list[GraphNode]:
        nodes = self._nodes.values()
        if types:
            nodes = (node for node in nodes if node.type in types)
        if language:
            nodes = (node for node in nodes if node.language == language)
        return list(nodes)

    def get_all_edges(self, types=None, min_confidence=0.0, include_provenances=None) -> list[GraphEdge]:
        edges = self._edges.values()
        if types:
            edges = (edge for edge in edges if edge.type in types)
        if min_confidence > 0:
            edges = (edge for edge in edges if edge.confidence >= min_confidence)
        if include_provenances:
            edges = (edge for edge in edges if edge.provenance in include_provenances)
        return list(edges)

    def get_edges_from(self, node_id: str, edge_types=None) -> list[GraphEdge]:
        edges = [self._edges[eid] for eid in self._out_edges.get(node_id, []) if eid in self._edges]
        if edge_types:
            edges = [edge for edge in edges if edge.type in edge_types]
        return edges

    def get_edges_to(self, node_id: str, edge_types=None) -> list[GraphEdge]:
        edges = [self._edges[eid] for eid in self._in_edges.get(node_id, []) if eid in self._edges]
        if edge_types:
            edges = [edge for edge in edges if edge.type in edge_types]
        return edges

    def find_nodes_by_name(self, name: str, limit: int = 20) -> list[GraphNode]:
        lowered = name.lower()
        return [
            node for node in self._nodes.values()
            if lowered in node.label.lower() or lowered in (node.qualified_name or "").lower()
        ][:limit]

    def shortest_path(self, from_id: str, to_id: str) -> list[str]:
        try:
            return nx.shortest_path(self._nx, from_id, to_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_file_fingerprint(self, file_path: str) -> Optional[str]:
        return self._fingerprints.get(file_path)

    def set_file_fingerprint(self, file_path: str, fingerprint: str) -> None:
        self._fingerprints[file_path] = fingerprint
        self._conn.execute(
            """
            INSERT INTO file_fingerprints(file_path, fingerprint)
            VALUES (?, ?)
            ON CONFLICT(file_path) DO UPDATE SET fingerprint=excluded.fingerprint
            """,
            (file_path, fingerprint),
        )
        self._conn.commit()

    def get_tracked_files(self) -> dict[str, str]:
        return dict(self._fingerprints)

    def remove_file_records(self, file_path: str) -> None:
        node_ids = {
            node.id for node in self._nodes.values()
            if node.file_path == file_path or node.id == f"file:{file_path}"
        }
        edge_ids = {
            edge.id for edge in self._edges.values()
            if edge.file_path == file_path or edge.source_id in node_ids or edge.target_id in node_ids
        }
        for edge_id in edge_ids:
            edge = self._edges.pop(edge_id, None)
            if not edge:
                continue
            if edge_id in self._out_edges.get(edge.source_id, []):
                self._out_edges[edge.source_id].remove(edge_id)
            if edge_id in self._in_edges.get(edge.target_id, []):
                self._in_edges[edge.target_id].remove(edge_id)
            if self._nx.has_edge(edge.source_id, edge.target_id):
                self._nx.remove_edge(edge.source_id, edge.target_id)
            self._conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
        for node_id in node_ids:
            self._nodes.pop(node_id, None)
            if self._nx.has_node(node_id):
                self._nx.remove_node(node_id)
            self._conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        self._fingerprints.pop(file_path, None)
        self._conn.execute("DELETE FROM file_fingerprints WHERE file_path = ?", (file_path,))
        self._conn.commit()

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
        edge_ids = [edge.id for edge in self._edges.values() if edge.provenance == ProvenanceTag.MODEL_ASSISTED_INFERENCE]
        for edge_id in edge_ids:
            edge = self._edges.pop(edge_id, None)
            if not edge:
                continue
            if edge_id in self._out_edges.get(edge.source_id, []):
                self._out_edges[edge.source_id].remove(edge_id)
            if edge_id in self._in_edges.get(edge.target_id, []):
                self._in_edges[edge.target_id].remove(edge_id)
            if self._nx.has_edge(edge.source_id, edge.target_id):
                self._nx.remove_edge(edge.source_id, edge.target_id)
            self._conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
        self._conn.commit()

    def get_stats(self) -> GraphStats:
        stats = GraphStats(node_count=len(self._nodes), edge_count=len(self._edges))
        for node in self._nodes.values():
            if node.type == NodeType.FILE:
                stats.file_count += 1
            elif node.type == NodeType.CLASS:
                stats.class_count += 1
            elif node.type == NodeType.FUNCTION:
                stats.function_count += 1
            elif node.type == NodeType.METHOD:
                stats.method_count += 1
        for edge in self._edges.values():
            if edge.type in (EdgeType.POSSIBLE_CALLS, EdgeType.POSSIBLE_REFERENCES):
                stats.unresolved_calls += 1
            if edge.provenance == ProvenanceTag.MODEL_ASSISTED_INFERENCE:
                stats.model_inferred_edges += 1
        return stats
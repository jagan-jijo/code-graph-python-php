import { memo, useEffect, useMemo, useRef, type CSSProperties } from 'react';
import dagre from 'dagre';
import {
	Background,
	Controls,
	Handle,
	MarkerType,
	MiniMap,
	Position,
	ReactFlow,
	type Edge,
	type Node,
	type NodeProps,
	type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import type { EdgeType, GraphEdge, GraphNode, GraphResponse } from '../types/graph';

interface GraphCanvasProps {
	graph: GraphResponse | null;
	isGraphLoading: boolean;
	projectStatus?: string | null;
	error?: string | null;
	showProvenanceBadges: boolean;
	groupByModules: boolean;
	selectedNodeId?: string | null;
	onSelectNode: (nodeId: string) => void;
}

interface GraphCardData extends Record<string, unknown> {
	typeLabel: string;
	isEntryPoint: boolean;
	title: string;
	signature: string;
	summary: string;
	cardStyle: CSSProperties;
}

const NODE_WIDTH = 280;
const NODE_HEIGHT = 138;
const secondaryEdgeTypes: EdgeType[] = ['CONTAINS', 'DEFINED_IN'];
const pipelineEdgeTypes: EdgeType[] = ['CALLS', 'POSSIBLE_CALLS'];
const modulePalette = ['#2f6c73', '#8d4f2e', '#567c3b', '#8a3d3d', '#5b5ea6', '#7b6a2d', '#9a4d7e', '#3f6d8f'];

const GraphCardNode = memo(function GraphCardNode({ data }: NodeProps<Node<GraphCardData>>) {
	const card = data as GraphCardData;
	return (
		<div className="graph-node-shell">
			<Handle type="target" position={Position.Top} className="graph-node-handle" />
			<div className="graph-node-card" style={card.cardStyle}>
				<div className="graph-node-topline">
					<span className="graph-node-type">{card.typeLabel}</span>
					{card.isEntryPoint ? <span className="graph-node-pill">entry</span> : null}
				</div>
				<strong className="graph-node-title">{card.title}</strong>
				{card.signature ? <div className="graph-node-signature">{card.signature}</div> : null}
				{card.summary ? <div className="graph-node-summary">{card.summary}</div> : null}
			</div>
			<Handle type="source" position={Position.Bottom} className="graph-node-handle" />
		</div>
	);
});

const nodeTypes = {
	graphCard: GraphCardNode,
};

function typeLabel(type: string): string {
	return type.replace(/_/g, ' ');
}

function truncate(value: string, maxLength: number): string {
	if (value.length <= maxLength) {
		return value;
	}
	return `${value.slice(0, maxLength - 1)}…`;
}

function describeNode(node: GraphNode): string {
	if (node.ai_summary?.trim()) {
		return node.ai_summary.trim();
	}
	if (node.docstring?.trim()) {
		return node.docstring.trim();
	}
	if (typeof node.properties?.module_name === 'string') {
		return String(node.properties.module_name);
	}
	return node.qualified_name ?? '';
}

function nodeWeight(node: GraphNode): number {
	const order: Record<string, number> = {
		repository: 0,
		directory: 1,
		file: 2,
		module: 3,
		class: 4,
		interface: 5,
		trait: 6,
		function: 7,
		method: 8,
	};
	return order[node.type] ?? 99;
}

function colorFromGroupId(groupId: string): string {
	let hash = 0;
	for (let index = 0; index < groupId.length; index += 1) {
		hash = (hash * 31 + groupId.charCodeAt(index)) >>> 0;
	}
	return modulePalette[hash % modulePalette.length];
}

function hexToRgba(hex: string, alpha: number): string {
	const value = hex.replace('#', '');
	const full = value.length === 3
		? value.split('').map((part) => `${part}${part}`).join('')
		: value;
	const red = Number.parseInt(full.slice(0, 2), 16);
	const green = Number.parseInt(full.slice(2, 4), 16);
	const blue = Number.parseInt(full.slice(4, 6), 16);
	return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function resolveContainerMap(nodes: GraphNode[], edges: GraphEdge[]): Map<string, string> {
	const map = new Map<string, string>();
	const nodeById = new Map(nodes.map((node) => [node.id, node]));

	for (const edge of edges) {
		if (edge.type === 'CONTAINS') {
			const source = nodeById.get(edge.source_id);
			const target = nodeById.get(edge.target_id);
			if (source && target && (source.type === 'module' || source.type === 'file') && target.type !== 'module' && target.type !== 'file' && target.type !== 'directory') {
				map.set(edge.target_id, edge.source_id);
			}
		}
	}

	for (const edge of edges) {
		if (edge.type === 'DEFINED_IN' && nodeById.has(edge.target_id)) {
			map.set(edge.source_id, map.get(edge.source_id) ?? edge.target_id);
		}
	}

	for (const node of nodes) {
		if (map.has(node.id)) {
			continue;
		}
		if ((node.type === 'function' || node.type === 'method' || node.type === 'class') && node.file_path) {
			const fallbackFile = nodes.find((candidate) => candidate.type === 'file' && candidate.file_path === node.file_path);
			if (fallbackFile) {
				map.set(node.id, fallbackFile.id);
			}
		}
	}

	return map;
}

function buildHighlightState(edges: GraphEdge[], selectedNodeId?: string | null) {
	const highlightedNodeIds = new Set<string>();
	const highlightedEdgeIds = new Set<string>();

	if (!selectedNodeId) {
		return { highlightedNodeIds, highlightedEdgeIds };
	}

	const outgoing = new Map<string, GraphEdge[]>();
	const incoming = new Map<string, GraphEdge[]>();

	for (const edge of edges) {
		if (!pipelineEdgeTypes.includes(edge.type)) {
			continue;
		}
		const outgoingEdges = outgoing.get(edge.source_id) ?? [];
		outgoingEdges.push(edge);
		outgoing.set(edge.source_id, outgoingEdges);

		const incomingEdges = incoming.get(edge.target_id) ?? [];
		incomingEdges.push(edge);
		incoming.set(edge.target_id, incomingEdges);
	}

	const queue = [selectedNodeId];
	const visited = new Set(queue);

	while (queue.length > 0) {
		const current = queue.shift();
		if (!current) {
			continue;
		}
		highlightedNodeIds.add(current);

		for (const edge of outgoing.get(current) ?? []) {
			highlightedEdgeIds.add(edge.id);
			highlightedNodeIds.add(edge.target_id);
			if (!visited.has(edge.target_id)) {
				visited.add(edge.target_id);
				queue.push(edge.target_id);
			}
		}

		for (const edge of incoming.get(current) ?? []) {
			highlightedEdgeIds.add(edge.id);
			highlightedNodeIds.add(edge.source_id);
			if (!visited.has(edge.source_id)) {
				visited.add(edge.source_id);
				queue.push(edge.source_id);
			}
		}
	}

	if (highlightedEdgeIds.size === 0) {
		highlightedNodeIds.add(selectedNodeId);
		for (const edge of edges) {
			if (edge.source_id === selectedNodeId || edge.target_id === selectedNodeId) {
				highlightedEdgeIds.add(edge.id);
				highlightedNodeIds.add(edge.source_id);
				highlightedNodeIds.add(edge.target_id);
			}
		}
	}

	for (const edge of edges) {
		if (!secondaryEdgeTypes.includes(edge.type)) {
			continue;
		}
		if (highlightedNodeIds.has(edge.source_id) || highlightedNodeIds.has(edge.target_id)) {
			highlightedEdgeIds.add(edge.id);
			highlightedNodeIds.add(edge.source_id);
			highlightedNodeIds.add(edge.target_id);
		}
	}

	return { highlightedNodeIds, highlightedEdgeIds };
}

function buildLanePositions(nodes: GraphNode[], baseNodes: Node[], containerMap: Map<string, string>): Map<string, { x: number; y: number }> {
	const baseNodeById = new Map(baseNodes.map((node) => [node.id, node]));
	const positions = new Map<string, { x: number; y: number }>();
	const grouped = new Map<string, GraphNode[]>();
	const standalone: GraphNode[] = [];

	const laneNodes = nodes
		.filter((node) => node.type === 'file' || node.type === 'module')
		.sort((left, right) => {
			const leftPath = String(left.properties?.relative_path ?? left.qualified_name ?? left.label);
			const rightPath = String(right.properties?.relative_path ?? right.qualified_name ?? right.label);
			return leftPath.localeCompare(rightPath);
		});

	for (const node of nodes) {
		const containerId = containerMap.get(node.id);
		if (!containerId || containerId === node.id) {
			if (node.type !== 'file' && node.type !== 'module' && node.type !== 'repository') {
				standalone.push(node);
			}
			continue;
		}
		const bucket = grouped.get(containerId) ?? [];
		bucket.push(node);
		grouped.set(containerId, bucket);
	}

	const laneWidth = 360;
	const laneStartY = 180;
	const laneGapY = 170;

	laneNodes.forEach((laneNode, index) => {
		const laneX = index * laneWidth;
		positions.set(laneNode.id, { x: laneX, y: 24 });
		const members = (grouped.get(laneNode.id) ?? []).sort((left, right) => {
			const leftY = baseNodeById.get(left.id)?.position?.y ?? 0;
			const rightY = baseNodeById.get(right.id)?.position?.y ?? 0;
			if (leftY !== rightY) {
				return leftY - rightY;
			}
			return nodeWeight(left) - nodeWeight(right) || left.label.localeCompare(right.label);
		});
		members.forEach((member, memberIndex) => {
			positions.set(member.id, { x: laneX, y: laneStartY + memberIndex * laneGapY });
		});
	});

	const fallbackX = Math.max(laneNodes.length, 1) * laneWidth;
	standalone
		.sort((left, right) => nodeWeight(left) - nodeWeight(right) || left.label.localeCompare(right.label))
		.forEach((node, index) => {
			positions.set(node.id, { x: fallbackX, y: 24 + index * laneGapY });
		});

	const repositoryNode = nodes.find((node) => node.type === 'repository');
	if (repositoryNode) {
		positions.set(repositoryNode.id, { x: Math.max((laneNodes.length - 1) * laneWidth * 0.5, 0), y: -140 });
	}

	return positions;
}

function layoutGraph(graph: GraphResponse, selectedNodeId?: string | null, groupByModules = false): { nodes: Node[]; edges: Edge[] } {
	const nodeIdSet = new Set(graph.nodes.map((node) => node.id));
	const validEdges = graph.edges.filter((edge) => nodeIdSet.has(edge.source_id) && nodeIdSet.has(edge.target_id));
	const { highlightedNodeIds, highlightedEdgeIds } = buildHighlightState(validEdges, selectedNodeId);
	const hasSelection = Boolean(selectedNodeId);
	const containerMap = resolveContainerMap(graph.nodes, validEdges);

	const dagreGraph = new dagre.graphlib.Graph();
	dagreGraph.setGraph({ rankdir: 'TB', nodesep: 44, ranksep: 120, marginx: 24, marginy: 24 });
	dagreGraph.setDefaultEdgeLabel(() => ({}));

	const sortedNodes = [...graph.nodes].sort((left, right) => nodeWeight(left) - nodeWeight(right) || left.label.localeCompare(right.label));
	sortedNodes.forEach((node) => {
		dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
	});
	validEdges.forEach((edge) => {
		dagreGraph.setEdge(edge.source_id, edge.target_id);
	});
	dagre.layout(dagreGraph);

	const baseNodes: Node[] = sortedNodes.map((node) => {
		const layout = dagreGraph.node(node.id);
		return {
			id: node.id,
			position: {
				x: (layout?.x ?? 0) - NODE_WIDTH / 2,
				y: (layout?.y ?? 0) - NODE_HEIGHT / 2,
			},
			data: {},
		};
	});

	const lanePositions = groupByModules ? buildLanePositions(sortedNodes, baseNodes, containerMap) : new Map<string, { x: number; y: number }>();
	const visibleEdges = validEdges.filter((edge) => graph.edges.length < 180 || !secondaryEdgeTypes.includes(edge.type));
	const baseNodeById = new Map(baseNodes.map((node) => [node.id, node]));

	const nodes: Node[] = sortedNodes.map((node) => {
		const position = lanePositions.get(node.id) ?? baseNodeById.get(node.id)?.position ?? { x: 0, y: 0 };
		const summary = truncate(describeNode(node), 120);
		const signature = node.signature ? truncate(node.signature, 70) : '';
		const isHighlighted = highlightedNodeIds.has(node.id);
		const isSelected = selectedNodeId === node.id;
		const containerId = containerMap.get(node.id) ?? (node.type === 'file' || node.type === 'module' ? node.id : `type:${node.type}`);
		const accent = colorFromGroupId(containerId);
		const cardStyle = {
			'--module-accent': accent,
			'--module-surface': isSelected ? hexToRgba(accent, 0.24) : isHighlighted ? hexToRgba(accent, 0.18) : hexToRgba(accent, 0.12),
			'--module-surface-strong': hexToRgba(accent, 0.20),
		} as CSSProperties;

		return {
			id: node.id,
			type: 'graphCard',
			position,
			sourcePosition: Position.Bottom,
			targetPosition: Position.Top,
			data: {
				typeLabel: typeLabel(node.type),
				isEntryPoint: Boolean(node.is_entry_point),
				title: truncate(node.label, 42),
				signature,
				summary,
				cardStyle,
			},
			style: {
				borderRadius: 18,
				padding: 0,
				width: NODE_WIDTH,
				height: NODE_HEIGHT,
				border: isSelected ? `2px solid ${accent}` : isHighlighted ? `1.5px solid ${hexToRgba(accent, 0.65)}` : `1px solid ${hexToRgba(accent, 0.24)}`,
				background: 'rgba(255, 251, 245, 0.98)',
				boxShadow: isSelected ? `0 18px 34px ${hexToRgba(accent, 0.22)}` : isHighlighted ? `0 18px 30px ${hexToRgba(accent, 0.16)}` : '0 16px 28px rgba(75, 54, 33, 0.08)',
				overflow: 'hidden',
				cursor: 'pointer',
			},
		};
	});

	const edges: Edge[] = visibleEdges.map((edge) => ({
		id: edge.id,
		source: edge.source_id,
		target: edge.target_id,
		label: secondaryEdgeTypes.includes(edge.type) ? '' : edge.type,
		animated: edge.type === 'POSSIBLE_CALLS',
		type: 'smoothstep',
		markerEnd: {
			type: MarkerType.ArrowClosed,
			width: 16,
			height: 16,
			color: highlightedEdgeIds.has(edge.id)
				? '#a04f24'
				: edge.provenance === 'model_assisted_inference'
					? '#bb5a2b'
					: secondaryEdgeTypes.includes(edge.type)
						? 'rgba(111, 125, 132, 0.25)'
						: '#6f7d84',
		},
		style: {
			stroke: highlightedEdgeIds.has(edge.id)
				? '#a04f24'
				: edge.provenance === 'model_assisted_inference'
					? '#bb5a2b'
					: secondaryEdgeTypes.includes(edge.type)
						? 'rgba(111, 125, 132, 0.25)'
						: '#6f7d84',
			strokeWidth: highlightedEdgeIds.has(edge.id) ? 3 : secondaryEdgeTypes.includes(edge.type) ? 1 : Math.max(1.5, edge.confidence * 2),
			opacity: hasSelection && !highlightedEdgeIds.has(edge.id) ? 0.38 : 1,
		},
		labelStyle: {
			fill: '#594431',
			fontWeight: 700,
			fontSize: 11,
		},
		data: {
			provenance: edge.provenance,
		},
	}));

	return { nodes, edges };
}

export function GraphCanvas({ graph, isGraphLoading, projectStatus, error, showProvenanceBadges, groupByModules, selectedNodeId, onSelectNode }: GraphCanvasProps) {
	const flow = useMemo(() => (graph ? layoutGraph(graph, selectedNodeId, groupByModules) : { nodes: [], edges: [] }), [graph, selectedNodeId, groupByModules]);
	const flowRef = useRef<ReactFlowInstance<Node, Edge> | null>(null);

	useEffect(() => {
		if (!flowRef.current || flow.nodes.length === 0) {
			return;
		}

		const frameId = window.requestAnimationFrame(() => {
			flowRef.current?.fitView({ padding: 0.16, includeHiddenNodes: true, duration: 300 });
		});

		return () => window.cancelAnimationFrame(frameId);
	}, [flow.nodes.length, flow.edges.length, groupByModules, selectedNodeId]);

	const graphStateMessage = useMemo(() => {
		if (isGraphLoading) {
			return 'Loading graph data…';
		}
		if (projectStatus === 'ready' && error && !graph) {
			return error;
		}
		if (projectStatus === 'ready' && !graph) {
			return 'The project is ready, but the graph is still being prepared.';
		}
		if (projectStatus === 'ready' && graph && flow.nodes.length === 0) {
			return 'No graph nodes or valid connections were returned for this project. Try changing the analysis depth, language, or current filters and run the analysis again.';
		}
		return 'Run an analysis to render the graph.';
	}, [error, flow.nodes.length, graph, isGraphLoading, projectStatus]);

	return (
		<div className="panel graph-panel">
			<div className="panel-header">
				<h2>Graph canvas</h2>
				<p>{selectedNodeId ? 'Selected node keeps the full call pipeline highlighted while the rest of the graph stays visible.' : groupByModules ? 'Functions are arranged in module lanes while call edges stay visible across modules.' : showProvenanceBadges ? 'Nodes show type, signature, and summary while structural edges are visually de-emphasized.' : 'Provenance badges hidden.'}</p>
			</div>
			{graph && graph.edges.length >= 180 ? (
				<div className="graph-note">
					Structural edges like `CONTAINS` and `DEFINED_IN` are muted to keep the canvas readable on larger graphs.
				</div>
			) : null}
			<div className="graph-surface">
				{!graph || flow.nodes.length === 0 ? (
					<div className="graph-empty-state">{graphStateMessage}</div>
				) : (
					<ReactFlow
						nodes={flow.nodes}
						edges={flow.edges}
						nodeTypes={nodeTypes}
						fitView
						fitViewOptions={{ padding: 0.16 }}
						nodesDraggable={false}
						nodesConnectable={false}
						onInit={(instance) => {
							flowRef.current = instance;
						}}
						onNodeClick={(_, node) => onSelectNode(node.id)}
					>
						<MiniMap pannable zoomable />
						<Controls />
						<Background gap={20} size={1} />
					</ReactFlow>
				)}
			</div>
		</div>
	);
}

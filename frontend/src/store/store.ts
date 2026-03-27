import { create } from 'zustand';

import type { GraphFilters, GraphResponse, GraphNode } from '../types/graph';
import type { ProgressEvent, Project } from '../types/project';

interface AppState {
  currentProject: Project | null;
  graph: GraphResponse | null;
  selectedNode: GraphNode | null;
  progressEvents: ProgressEvent[];
  isLoading: boolean;
  error: string | null;
  filters: GraphFilters;
  setProject: (project: Project | null) => void;
  setGraph: (graph: GraphResponse | null) => void;
  setSelectedNode: (node: GraphNode | null) => void;
  pushProgress: (event: ProgressEvent) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setFilters: (partial: Partial<GraphFilters>) => void;
  resetProgress: () => void;
}

const defaultFilters: GraphFilters = {
  minConfidence: 0.3,
  q: '',
  includeParserFacts: true,
  includeReferenceFacts: true,
  includeGraphInference: true,
  includeModelInference: true,
  hideNativeLibraryNodes: false,
  hideThirdPartyDependencyNodes: false,
  showProvenanceBadges: true,
  groupByModules: false,
};

export const useAppStore = create<AppState>((set) => ({
  currentProject: null,
  graph: null,
  selectedNode: null,
  progressEvents: [],
  isLoading: false,
  error: null,
  filters: defaultFilters,
  setProject: (currentProject: Project | null) => set({ currentProject }),
  setGraph: (graph: GraphResponse | null) => set({ graph }),
  setSelectedNode: (selectedNode: GraphNode | null) => set({ selectedNode }),
  pushProgress: (event: ProgressEvent) => set((state: AppState) => ({ progressEvents: [...state.progressEvents.slice(-49), event] })),
  setLoading: (isLoading: boolean) => set({ isLoading }),
  setError: (error: string | null) => set({ error }),
  setFilters: (partial: Partial<GraphFilters>) => set((state: AppState) => ({ filters: { ...state.filters, ...partial } })),
  resetProgress: () => set({ progressEvents: [] }),
}));
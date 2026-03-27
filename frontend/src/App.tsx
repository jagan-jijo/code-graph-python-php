import { useState } from 'react';

import { GraphView } from './components/GraphView.tsx';
import { NodeDetail } from './components/NodeDetail';
import { ProgressView } from './components/ProgressView';
import { SearchPanel } from './components/SearchPanel';
import { SetupForm } from './components/SetupForm';
import { Toolbar } from './components/Toolbar';
import { useGraph } from './hooks/useGraph';
import { useProject } from './hooks/useProject';
import { getNode, refineGraph } from './services/api';
import { useAppStore } from './store/store';
import type { IndexRequest } from './types/project';

export default function App() {
  const { currentProject, startIndexing, stopIndexing } = useProject();
  const { graph, isGraphLoading } = useGraph();
  const {
    selectedNode,
    setSelectedNode,
    progressEvents,
    filters,
    setFilters,
    error,
    setError,
    isLoading,
  } = useAppStore();
  const [refineStatus, setRefineStatus] = useState('');

  async function handleStart(payload: IndexRequest) {
    const project = await startIndexing(payload);
    if (project.status === 'error') {
      setError(project.error_message ?? 'Indexing failed');
    }
  }

  async function handleSelectNode(nodeId: string) {
    if (!currentProject) {
      return;
    }
    const result = await getNode(currentProject.id, nodeId);
    setSelectedNode(result.node);
  }

  async function handleRefine() {
    if (!currentProject) {
      return;
    }
    try {
      await refineGraph(currentProject.id);
      setRefineStatus('Refinement request completed. Reloaded summaries appear on refreshed graph data.');
    } catch (refineError) {
      setRefineStatus(refineError instanceof Error ? refineError.message : 'Refinement failed.');
    }
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <main className="app-grid">
        <div className="left-column">
          <SetupForm onStart={handleStart} />
          <SearchPanel value={filters.q} onChange={(value) => setFilters({ q: value })} />
          <Toolbar
            minConfidence={filters.minConfidence}
            showProvenanceBadges={filters.showProvenanceBadges}
            groupByModules={filters.groupByModules}
            includeParserFacts={filters.includeParserFacts}
            includeReferenceFacts={filters.includeReferenceFacts}
            includeGraphInference={filters.includeGraphInference}
            includeModelInference={filters.includeModelInference}
            hideNativeLibraryNodes={filters.hideNativeLibraryNodes}
            hideThirdPartyDependencyNodes={filters.hideThirdPartyDependencyNodes}
            stats={graph?.stats}
            onChange={setFilters}
            onRefine={handleRefine}
          />
          {error ? <div className="panel error-panel">{error}</div> : null}
          {refineStatus ? <div className="panel info-panel">{refineStatus}</div> : null}
        </div>

        <div className="center-column">
          <ProgressView
            events={progressEvents}
            isLoading={isLoading}
            projectStatus={currentProject?.status ?? null}
            onStop={stopIndexing}
          />
          <GraphView
            graph={graph}
            isGraphLoading={isGraphLoading}
            projectStatus={currentProject?.status ?? null}
            error={error}
            showProvenanceBadges={filters.showProvenanceBadges}
            groupByModules={filters.groupByModules}
            selectedNodeId={selectedNode?.id ?? null}
            onSelectNode={handleSelectNode}
          />
        </div>

        <div className="right-column">
          <NodeDetail
            projectId={currentProject?.id ?? null}
            node={selectedNode}
            graphEdges={graph?.edges ?? []}
          />
        </div>
      </main>
      <footer className="app-footer">
        <span>Created by Jagan Jijo</span>
        <a href="https://jagan-jijo.github.io/portfolio/" target="_blank" rel="noreferrer">
          jagan-jijo.github.io/portfolio/
        </a>
      </footer>
    </div>
  );
}
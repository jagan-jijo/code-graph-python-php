import type { GraphStats } from '../types/graph';

interface ToolbarProps {
  minConfidence: number;
  showProvenanceBadges: boolean;
  groupByModules: boolean;
  includeParserFacts: boolean;
  includeReferenceFacts: boolean;
  includeGraphInference: boolean;
  includeModelInference: boolean;
  hideNativeLibraryNodes: boolean;
  hideThirdPartyDependencyNodes: boolean;
  stats?: GraphStats;
  onChange: (partial: {
    minConfidence?: number;
    showProvenanceBadges?: boolean;
    groupByModules?: boolean;
    includeParserFacts?: boolean;
    includeReferenceFacts?: boolean;
    includeGraphInference?: boolean;
    includeModelInference?: boolean;
    hideNativeLibraryNodes?: boolean;
    hideThirdPartyDependencyNodes?: boolean;
  }) => void;
  onRefine: () => Promise<void>;
}

export function Toolbar(props: ToolbarProps) {
  const {
    minConfidence,
    showProvenanceBadges,
    groupByModules,
    includeParserFacts,
    includeReferenceFacts,
    includeGraphInference,
    includeModelInference,
    hideNativeLibraryNodes,
    hideThirdPartyDependencyNodes,
    stats,
    onChange,
    onRefine,
  } = props;

  return (
    <section className="panel compact-panel">
      <div className="panel-header">
        <h2>Graph controls</h2>
        <p>{stats ? `${stats.node_count} nodes / ${stats.edge_count} edges` : 'No graph loaded yet.'}</p>
      </div>
      <div className="toolbar-grid">
        <label><input type="checkbox" checked={includeParserFacts} onChange={(event) => onChange({ includeParserFacts: event.target.checked })} /> Parser facts only</label>
        <label><input type="checkbox" checked={includeReferenceFacts} onChange={(event) => onChange({ includeReferenceFacts: event.target.checked })} /> Parser + reference resolution</label>
        <label><input type="checkbox" checked={includeGraphInference} onChange={(event) => onChange({ includeGraphInference: event.target.checked })} /> Graph algorithm inference</label>
        <label><input type="checkbox" checked={includeModelInference} onChange={(event) => onChange({ includeModelInference: event.target.checked })} /> Show model-assisted inferred edges</label>
        <label><input type="checkbox" checked={hideNativeLibraryNodes} onChange={(event) => onChange({ hideNativeLibraryNodes: event.target.checked })} /> Hide native / built-in Python library nodes</label>
        <label><input type="checkbox" checked={hideThirdPartyDependencyNodes} onChange={(event) => onChange({ hideThirdPartyDependencyNodes: event.target.checked })} /> Hide third-party package dependency nodes</label>
        <label><input type="checkbox" checked={showProvenanceBadges} onChange={(event) => onChange({ showProvenanceBadges: event.target.checked })} /> Show provenance badges on every edge</label>
        <label><input type="checkbox" checked={groupByModules} onChange={(event) => onChange({ groupByModules: event.target.checked })} /> Group functions by module lane</label>
        <label>
          Hide inferred edges below confidence threshold
          <input type="range" min="0" max="1" step="0.05" value={minConfidence} onChange={(event) => onChange({ minConfidence: Number(event.target.value) })} />
        </label>
      </div>
      <div className="button-row">
        <button className="secondary-button" type="button" onClick={onRefine}>Run refinement</button>
      </div>
    </section>
  );
}
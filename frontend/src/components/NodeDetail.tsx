import { useEffect, useState } from 'react';

import { getSourceSnippet } from '../services/api';
import type { GraphEdge, GraphNode } from '../types/graph';

interface NodeDetailProps {
  projectId: string | null;
  node: GraphNode | null;
  graphEdges: GraphEdge[];
}

export function NodeDetail({ projectId, node, graphEdges }: NodeDetailProps) {
  const [snippet, setSnippet] = useState('');

  useEffect(() => {
    if (!projectId || !node?.file_path) {
      setSnippet('');
      return;
    }
    getSourceSnippet(projectId, node.file_path, node.line_start ?? 1, node.line_end ?? (node.line_start ?? 1) + 30)
      .then((result) => setSnippet(result.snippet))
      .catch(() => setSnippet('Source snippet unavailable.'));
  }, [node, projectId]);

  if (!node) {
    return (
      <aside className="panel detail-panel">
        <div className="panel-header">
          <h2>Node details</h2>
          <p>Select a node to inspect callers, callees, metadata, and source.</p>
        </div>
      </aside>
    );
  }

  const callers = graphEdges.filter((edge) => edge.target_id === node.id);
  const callees = graphEdges.filter((edge) => edge.source_id === node.id);

  return (
    <aside className="panel detail-panel">
      <div className="panel-header">
        <h2>{node.label}</h2>
        <p>{node.qualified_name ?? node.type}</p>
      </div>

      <div className="detail-grid">
        <div>
          <strong>Type</strong>
          <p>{node.type}</p>
        </div>
        <div>
          <strong>Signature</strong>
          <p>{node.signature ?? 'Not available'}</p>
        </div>
        <div>
          <strong>Confidence</strong>
          <p>{node.confidence.toFixed(2)}</p>
        </div>
        <div>
          <strong>Provenance</strong>
          <p>{node.provenance}</p>
        </div>
        <div>
          <strong>Hotspot</strong>
          <p>{(node.hotspot_score ?? 0).toFixed(2)}</p>
        </div>
      </div>

      {node.docstring ? (
        <section>
          <h3>Description</h3>
          <p>{node.docstring}</p>
        </section>
      ) : null}

      {node.ai_summary ? (
        <section>
          <h3>AI summary</h3>
          <p>{node.ai_summary}</p>
        </section>
      ) : null}

      <section>
        <h3>Callers</h3>
        {callers.length ? callers.map((edge) => <p key={edge.id}>{`${edge.source_id} -> ${edge.type}`}</p>) : <p>No callers in current view.</p>}
      </section>

      <section>
        <h3>Callees</h3>
        {callees.length ? callees.map((edge) => <p key={edge.id}>{`${edge.type} -> ${edge.target_id}`}</p>) : <p>No callees in current view.</p>}
      </section>

      <section>
        <h3>Source snippet</h3>
        <pre>{snippet}</pre>
      </section>
    </aside>
  );
}
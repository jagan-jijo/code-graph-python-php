import type { ProgressEvent } from '../types/project';

interface ProgressViewProps {
  events: ProgressEvent[];
  isLoading: boolean;
  projectStatus?: string | null;
  onStop?: () => Promise<unknown>;
}

export function ProgressView({ events, isLoading, projectStatus, onStop }: ProgressViewProps) {
  const latest = events[events.length - 1];
  const title = isLoading ? 'Indexing progress' : 'Progress';
  const isCancelled = projectStatus === 'cancelled';
  const subtitle = latest
    ? latest.message
    : isLoading
      ? 'Preparing analysis request…'
      : 'Waiting to start analysis.';
  const progressPercent = Math.round((latest?.progress ?? 0) * 100);
  const hasFileProgress = Boolean(latest && latest.files_total > 0);

  return (
    <section className="panel compact-panel progress-panel">
      <div className="progress-header-row">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
        <span className={`progress-pill ${isLoading ? 'progress-pill-active' : ''}`}>
          {projectStatus ?? (isLoading ? 'starting' : 'idle')}
        </span>
      </div>
      <div className="progress-strip">
        <div className="progress-strip-head">
          <div className="progress-stage-name">{latest?.stage ?? (isLoading ? 'starting' : 'idle')}</div>
          <div className="progress-strip-actions">
            <div className="progress-strip-metrics">
              {hasFileProgress ? <span>{latest?.files_processed ?? 0} / {latest?.files_total ?? 0} files</span> : null}
              <strong>{progressPercent}%</strong>
            </div>
            {isLoading && onStop ? (
              <button type="button" className="secondary-button progress-stop-button" onClick={() => void onStop()}>
                Stop analysis
              </button>
            ) : null}
          </div>
        </div>
        <div className="progress-bar progress-bar-large">
          <div className={`progress-fill ${isLoading ? 'progress-fill-active' : ''}`} style={{ width: `${progressPercent}%` }} />
        </div>
        {isLoading ? (
          <div className="progress-orbit" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {isCancelled ? (
          <div className="progress-status-note progress-status-note-cancelled">
            Cancelled. You can change parameters and start analysis again.
          </div>
        ) : null}
      </div>
    </section>
  );
}
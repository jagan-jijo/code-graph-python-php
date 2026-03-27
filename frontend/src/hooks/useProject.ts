import { useEffect, useRef } from 'react';

import { cancelProject, connectProgress, createProject, getProjectStatus } from '../services/api';
import { useAppStore } from '../store/store';
import type { IndexRequest } from '../types/project';

export function useProject() {
  const socketRef = useRef<WebSocket | null>(null);
  const runTokenRef = useRef(0);
  const {
    currentProject,
    setProject,
    pushProgress,
    setLoading,
    setError,
    resetProgress,
  } = useAppStore();

  useEffect(() => () => socketRef.current?.close(), []);

  async function startIndexing(payload: IndexRequest) {
    const runToken = runTokenRef.current + 1;
    runTokenRef.current = runToken;
    resetProgress();
    setError(null);
    setLoading(true);
    pushProgress({
      project_id: 'pending',
      stage: 'submit',
      message: 'Submitting analysis request…',
      progress: 0.02,
      files_processed: 0,
      files_total: 0,
      error: null,
    });
    const project = await createProject(payload);
    if (runTokenRef.current !== runToken) {
      return project;
    }
    setProject(project);
    pushProgress({
      project_id: project.id,
      stage: 'queued',
      message: 'Analysis request accepted. Waiting for indexing updates…',
      progress: 0.05,
      files_processed: 0,
      files_total: 0,
      error: null,
    });
    socketRef.current?.close();
    socketRef.current = connectProgress(project.id, (event) => {
      pushProgress(event);
    });

    let latest = project;
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      if (runTokenRef.current !== runToken) {
        break;
      }
      latest = await getProjectStatus(project.id);
      if (runTokenRef.current !== runToken) {
        break;
      }
      setProject(latest);
      pushProgress({
        project_id: project.id,
        stage: 'status',
        message: `Project status: ${latest.status}`,
        progress: latest.status === 'ready' || latest.status === 'error' ? 1 : latest.status === 'cancelled' ? 0 : 0.08,
        files_processed: latest.file_count,
        files_total: latest.file_count,
        error: latest.error_message ?? null,
      });
      if (latest.status === 'ready' || latest.status === 'error' || latest.status === 'cancelled') {
        break;
      }
    }
    if (runTokenRef.current === runToken) {
      setLoading(false);
    }
    return latest;
  }

  async function stopIndexing() {
    if (!currentProject || currentProject.status !== 'indexing') {
      return currentProject;
    }
    runTokenRef.current += 1;
    const project = await cancelProject(currentProject.id);
    socketRef.current?.close();
    socketRef.current = null;
    setProject(project);
    pushProgress({
      project_id: project.id,
      stage: 'cancelled',
      message: 'Analysis stopped. You can adjust parameters and start again.',
      progress: 0,
      files_processed: 0,
      files_total: 0,
      error: null,
    });
    setLoading(false);
    return project;
  }

  return { currentProject, startIndexing, stopIndexing };
}
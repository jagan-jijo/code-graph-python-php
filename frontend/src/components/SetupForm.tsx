import { useDeferredValue, useMemo, useState, type FormEvent } from 'react';

import { browseFiles, listModels, testModelConnection } from '../services/api';
import type { AnalysisProvider, BrowseFile, IndexRequest, ModelConfig, ProjectConfig } from '../types/project';
import './SetupForm.css';

interface SetupFormProps {
  onStart: (payload: IndexRequest) => Promise<void>;
}

const defaultModelConfig: ModelConfig = {
  provider_type: 'ollama_native_api',
  base_url: 'http://localhost:11434',
  api_key: '',
  remote_send_policy: 'graph_metadata_plus_selected_snippets',
  planner_model: '',
  code_model: '',
  query_model: '',
};

const providerDefaults: Record<Exclude<AnalysisProvider, 'native'>, Pick<ModelConfig, 'provider_type' | 'base_url' | 'api_key'>> = {
  ollama: {
    provider_type: 'ollama_native_api',
    base_url: 'http://localhost:11434',
    api_key: '',
  },
  openwebui: {
    provider_type: 'openwebui_api',
    base_url: 'http://localhost:3001',
    api_key: '',
  },
};

function parseTags(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function isLocalBaseUrl(url: string): boolean {
  return /localhost|127\.0\.0\.1|0\.0\.0\.0/i.test(url);
}

function pickCodeModel(models: string[]): string {
  const coderModel = models.find((model) => /coder|code/i.test(model));
  return coderModel ?? models[0] ?? '';
}

function pickGeneralModel(models: string[]): string {
  return models[0] ?? '';
}

function getProviderLabel(provider: AnalysisProvider): string {
  if (provider === 'native') {
    return 'Native only';
  }
  if (provider === 'openwebui') {
    return 'Open WebUI';
  }
  return 'Ollama';
}

export function SetupForm({ onStart }: SetupFormProps) {
  const [name, setName] = useState('Local Code Graph');
  const [path, setPath] = useState('');
  const [language, setLanguage] = useState('python');
  const [entryPoints, setEntryPoints] = useState('');
  const [excludePatterns, setExcludePatterns] = useState('node_modules,.venv,__pycache__,.git');
  const [analysisDepth, setAnalysisDepth] = useState<ProjectConfig['analysis_depth']>('balanced');
  const [graphBackend, setGraphBackend] = useState<ProjectConfig['graph_backend']>('sqlite');
  const [analysisProvider, setAnalysisProvider] = useState<AnalysisProvider>('native');
  const [modelConfig, setModelConfig] = useState<ModelConfig>(defaultModelConfig);
  const [availableFiles, setAvailableFiles] = useState<BrowseFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browseError, setBrowseError] = useState('');
  const [browseQuery, setBrowseQuery] = useState('');
  const [browseVisibleCount, setBrowseVisibleCount] = useState(150);
  const [modelStatus, setModelStatus] = useState('');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelActionLoading, setModelActionLoading] = useState<'test' | 'list' | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const deferredBrowseQuery = useDeferredValue(browseQuery);

  const filteredFiles = useMemo(() => {
    const query = deferredBrowseQuery.trim().toLowerCase();
    if (!query) {
      return availableFiles;
    }
    return availableFiles.filter((file) => file.relative_path.toLowerCase().includes(query));
  }, [availableFiles, deferredBrowseQuery]);

  const visibleFiles = useMemo(
    () => filteredFiles.slice(0, browseVisibleCount),
    [filteredFiles, browseVisibleCount],
  );
  const usesModelRefinement = analysisProvider !== 'native';

  async function handleBrowse() {
    if (!path.trim()) {
      setBrowseError('Set a codebase path before browsing files.');
      return;
    }
    setBrowseOpen(true);
    setBrowseLoading(true);
    setBrowseError('');
    setBrowseQuery('');
    setBrowseVisibleCount(150);
    try {
      const result = await browseFiles(path.trim(), language, 400);
      setAvailableFiles(result.files);
      if (result.files.length === 0) {
        setBrowseError('No matching source files were found for this path and language.');
      } else if (result.source_type === 'github_url') {
        setBrowseError(`Browsing cached checkout for ${result.source_url ?? path.trim()}`);
      }
    } catch (error) {
      setAvailableFiles([]);
      setBrowseError(error instanceof Error ? error.message : 'Failed to load files.');
    } finally {
      setBrowseLoading(false);
    }
  }

  async function handleTestConnection() {
    if (!usesModelRefinement) {
      setModelStatus('Native analysis uses local parsers only. No model connection is required.');
      return;
    }
    setModelActionLoading('test');
    setModelStatus('');
    try {
      const result = await testModelConnection(modelConfig);
      setModelStatus(result.ok ? 'Model endpoint reachable.' : 'Model endpoint did not respond successfully.');
    } catch (error) {
      setModelStatus(error instanceof Error ? error.message : 'Failed to test model connection.');
    } finally {
      setModelActionLoading(null);
    }
  }

  async function handleListModels() {
    if (!usesModelRefinement) {
      setModelStatus('Native analysis does not use model endpoints.');
      return;
    }
    setModelActionLoading('list');
    setModelStatus('');
    try {
      const result = await listModels(modelConfig);
      setAvailableModels(result.models);
      if (result.models.length === 0) {
        setModelStatus('No models were returned by the endpoint.');
        return;
      }

      const generalModel = pickGeneralModel(result.models);
      const codeModel = pickCodeModel(result.models);
      setModelConfig((current) => ({
        ...current,
        planner_model: current.planner_model || generalModel,
        code_model: current.code_model || codeModel,
        query_model: current.query_model || generalModel,
      }));
      setModelStatus(`Loaded ${result.models.length} models and filled the empty model fields.`);
    } catch (error) {
      setAvailableModels([]);
      setModelStatus(error instanceof Error ? error.message : 'Failed to load models.');
    } finally {
      setModelActionLoading(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const config: ProjectConfig = {
        entry_points: parseTags(entryPoints),
        focus_modules: selectedFiles,
        exclude_patterns: parseTags(excludePatterns),
        analysis_depth: analysisDepth,
        graph_backend: graphBackend,
        construction_mode: usesModelRefinement ? 'native_plus_model_refinement' : 'native_only',
        model_config_data: usesModelRefinement ? modelConfig : null,
      };

      await onStart({
        name,
        path: path.trim(),
        language,
        config,
      });
    } finally {
      setSubmitting(false);
    }
  }

  function handleProviderChange(nextProvider: AnalysisProvider) {
    setAnalysisProvider(nextProvider);
    setAvailableModels([]);
    setModelStatus('');
    if (nextProvider === 'native') {
      return;
    }
    setModelConfig((current) => ({
      ...current,
      ...providerDefaults[nextProvider],
      planner_model: current.planner_model ?? '',
      code_model: current.code_model ?? '',
      query_model: current.query_model ?? '',
      remote_send_policy: current.remote_send_policy ?? 'graph_metadata_plus_selected_snippets',
    }));
  }

  function toggleFile(relativePath: string) {
    setSelectedFiles((current: string[]) => (
      current.includes(relativePath)
        ? current.filter((item: string) => item !== relativePath)
        : [...current, relativePath]
    ));
  }

  return (
    <section className="setup-card">
      <div className="setup-header">
        <h1>Code Graph Builder</h1>
        <p>Local-first static graph extraction with optional model-assisted refinement.</p>
      </div>

      <form className="setup-form" onSubmit={handleSubmit}>
        <label>
          <span>Project name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>

        <label>
          <span>Codebase path</span>
          <input
            placeholder="D:/path/to/repo or https://github.com/owner/repo"
            value={path}
            onChange={(event) => setPath(event.target.value)}
          />
        </label>

        <p className="field-help github-help">
          You can analyze a local folder or a public GitHub repository URL. GitHub repositories are fetched into the local cache before indexing.
        </p>

        <div className="setup-grid two-col">
          <label>
            <span>Primary language</span>
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="python">Python</option>
              <option value="php">PHP</option>
              <option value="mixed">Mixed</option>
            </select>
          </label>

          <label>
            <span>Analysis depth</span>
            <select value={analysisDepth} onChange={(event) => setAnalysisDepth(event.target.value as ProjectConfig['analysis_depth'])}>
              <option value="fast">Fast</option>
              <option value="balanced">Balanced</option>
              <option value="deep">Deep</option>
            </select>
          </label>
        </div>

        <div className="setup-grid two-col">
          <label>
            <span>Graph backend</span>
            <select value={graphBackend} onChange={(event) => setGraphBackend(event.target.value as ProjectConfig['graph_backend'])}>
              <option value="sqlite">SQLite (local persistent)</option>
              <option value="in_memory">In Memory</option>
            </select>
          </label>

          <label>
            <span>Analysis provider</span>
            <select value={analysisProvider} onChange={(event) => handleProviderChange(event.target.value as AnalysisProvider)}>
              <option value="native">Native</option>
              <option value="ollama">Ollama</option>
              <option value="openwebui">Open WebUI</option>
            </select>
          </label>
        </div>

        <label>
          <span>Entry points</span>
          <input
            placeholder="main, app, cli"
            value={entryPoints}
            onChange={(event) => setEntryPoints(event.target.value)}
          />
        </label>

        <label>
          <span>Exclude patterns</span>
          <input
            value={excludePatterns}
            onChange={(event) => setExcludePatterns(event.target.value)}
          />
        </label>

        <div className="focus-section">
          <div>
            <span className="field-title">Focus modules</span>
            <p className="field-help">Browse the selected codebase and pick `.py` or `.php` files to prioritize in the initial graph.</p>
          </div>
          <button type="button" className="secondary-button" onClick={handleBrowse}>Browse files</button>
        </div>

        {selectedFiles.length > 0 ? (
          <div className="selected-tags">
            {selectedFiles.map((file) => (
              <button key={file} type="button" className="tag" onClick={() => toggleFile(file)}>
                {file}
              </button>
            ))}
          </div>
        ) : null}

        <section className="model-section">
          <div className="section-title-row">
            <div>
              <h2>Model refinement</h2>
              <p className="field-help model-help">Choose local or remote model-assisted refinement and map models without crowding the form.</p>
            </div>
            <span className={usesModelRefinement && isLocalBaseUrl(modelConfig.base_url) ? 'badge local' : 'badge remote'}>
              {usesModelRefinement ? getProviderLabel(analysisProvider) : 'Disabled'}
            </span>
          </div>

          {!usesModelRefinement ? (
            <div className="privacy-banner">
              Native mode uses only the local parser and graph pipeline. No AI model calls are made.
            </div>
          ) : !isLocalBaseUrl(modelConfig.base_url) ? (
            <div className="privacy-banner">
              Remote inference may send graph metadata or selected snippets off-machine. Parser facts still remain authoritative.
            </div>
          ) : null}

          {usesModelRefinement ? (
            <>
              <div className="setup-grid three-col model-picker-grid">
                <label className="model-picker-field">
                  <span>Planner model</span>
                  <select
                    value={modelConfig.planner_model ?? ''}
                    onChange={(event) => setModelConfig((current) => ({ ...current, planner_model: event.target.value }))}
                  >
                    <option value="">Auto / first available</option>
                    {availableModels.map((model) => <option key={`planner-${model}`} value={model}>{model}</option>)}
                  </select>
                </label>

                <label className="model-picker-field">
                  <span>Code model</span>
                  <select
                    value={modelConfig.code_model ?? ''}
                    onChange={(event) => setModelConfig((current) => ({ ...current, code_model: event.target.value }))}
                  >
                    <option value="">Auto / coder-preferred</option>
                    {availableModels.map((model) => <option key={`code-${model}`} value={model}>{model}</option>)}
                  </select>
                </label>

                <label className="model-picker-field">
                  <span>Query model</span>
                  <select
                    value={modelConfig.query_model ?? ''}
                    onChange={(event) => setModelConfig((current) => ({ ...current, query_model: event.target.value }))}
                  >
                    <option value="">Auto / first available</option>
                    {availableModels.map((model) => <option key={`query-${model}`} value={model}>{model}</option>)}
                  </select>
                </label>
              </div>

              <div className="model-action-row">
                <div className="button-row model-buttons">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleTestConnection}
                    disabled={modelActionLoading !== null}
                  >
                    {modelActionLoading === 'test' ? 'Testing…' : 'Test connection'}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={handleListModels}
                    disabled={modelActionLoading !== null}
                  >
                    {modelActionLoading === 'list' ? 'Loading…' : 'List models'}
                  </button>
                </div>
              </div>
              <div className={`model-status ${modelStatus ? 'model-status-visible' : ''}`}>
                <strong className="model-status-title">Model status</strong>
                <span>{modelStatus || 'Model connection status and model discovery results will appear here.'}</span>
              </div>
            </>
          ) : null}

          {availableModels.length > 0 ? (
            <div className="available-models">
              {availableModels.map((model) => (
                <button
                  key={model}
                  type="button"
                  className="tag"
                  onClick={() => setModelConfig((current) => ({ ...current, code_model: model, planner_model: current.planner_model || model, query_model: current.query_model || model }))}
                >
                  {model}
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <button className="primary-button" type="submit" disabled={submitting || !path.trim()}>
          {submitting ? 'Analysing…' : 'Analyse codebase'}
        </button>
      </form>

      {browseOpen ? (
        <div
          className="browse-modal"
          role="dialog"
          aria-modal="true"
          onClick={() => setBrowseOpen(false)}
        >
          <div
            className="browse-panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="section-title-row">
              <h2>Choose focus files</h2>
              <button type="button" className="secondary-button" onClick={() => setBrowseOpen(false)}>Close</button>
            </div>
            <input
              className="browse-search"
              placeholder="Filter files"
              value={browseQuery}
              onChange={(event) => {
                setBrowseQuery(event.target.value);
                setBrowseVisibleCount(150);
              }}
            />
            <div className="browse-summary">
              <span>{browseLoading ? 'Loading files…' : `${filteredFiles.length} matching files`}</span>
              {selectedFiles.length > 0 ? <span>{selectedFiles.length} selected</span> : null}
            </div>
            {browseError ? <div className="browse-error">{browseError}</div> : null}
            <div className="browse-list">
              {visibleFiles.map((file) => (
                <label key={file.path} className="browse-item">
                  <input
                    type="checkbox"
                    checked={selectedFiles.includes(file.relative_path)}
                    onChange={() => toggleFile(file.relative_path)}
                  />
                  <span>{file.relative_path}</span>
                </label>
              ))}
            </div>
            {!browseLoading && visibleFiles.length < filteredFiles.length ? (
              <button
                type="button"
                className="secondary-button"
                onClick={() => setBrowseVisibleCount((current) => current + 150)}
              >
                Load more
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
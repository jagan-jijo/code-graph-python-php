# Code Graph Builder

Created and maintained by Jagan Jijo.

Portfolio: https://jagan-jijo.github.io/portfolio/

Code Graph Builder is a local-first codebase analysis tool with a FastAPI backend and a React frontend.

It indexes a repository, builds a navigable code graph, and lets you:

- analyze Python and PHP codebases
- inspect files, modules, classes, functions, and methods
- explore call, reference, import, and inheritance relationships
- filter the graph to focus on code you wrote
- optionally use Ollama, Open WebUI, or another OpenAI-compatible endpoint for model-assisted graph refinement

This project is designed to run on a developer machine. Users can point it at their own local or self-hosted model endpoints.

## What the app does

The app has two parts:

- Backend: scans a project, parses source files, builds graph nodes and edges, and exposes HTTP and WebSocket APIs
- Frontend: provides the setup form, graph viewer, filters, node details, and progress UI

Current graph features include:

- repository, directory, file, and module structure
- classes, functions, methods, interfaces, and traits
- imports and module usage
- call graph edges and unresolved call placeholders
- inheritance edges
- semantic reference hints for Python when available
- graph filters for inferred edges, provenance, grouping, native library nodes, and third-party dependency nodes

## Requirements

- Python 3.11+
- Node.js 18+
- npm

## Project layout

- [backend](backend): FastAPI API, indexing pipeline, parsers, graph storage, model adapters
- [frontend](frontend): React + TypeScript + Vite UI
- [start.ps1](start.ps1): Windows startup helper
- [start.cmd](start.cmd): Windows wrapper for PowerShell startup
- [start.sh](start.sh): macOS/Linux startup helper
- [requirements.txt](requirements.txt): Python dependencies
- [package.json](package.json): root scripts for backend and frontend

## Quick start

### Windows

From the project root:

```powershell
start.cmd
```

Or:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

### macOS / Linux

From the project root:

```bash
chmod +x ./start.sh
./start.sh
```

## Manual start

If you prefer to run each part yourself:

### 1. Create the virtual environment and install backend dependencies

Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
```

macOS / Linux:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

### 2. Install frontend dependencies

Root dependencies:

```bash
npm install
```

Frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

### 3. Start the app

Run both backend and frontend:

```bash
npm start
```

This starts:

- backend API on `http://127.0.0.1:8000`
- frontend UI on `http://127.0.0.1:3000`

## Configuration

The backend reads configuration from environment variables in [backend/config.py](backend/config.py). It also loads a root `.env` file automatically.

Recommended setup:

1. Copy `.env.example` to `.env`
2. Fill in only the values you need
3. Start the app

Example:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### Core settings

- `HOST`: backend bind address, default `127.0.0.1`
- `PORT`: backend port, default `8000`
- `PROJECTS_DIR`: where indexed project data is stored. If empty, the app uses the user home directory default.
- `GRAPH_BACKEND`: graph storage backend, default `sqlite`

### Model provider settings

The app supports three provider styles:

- Ollama native API
- Open WebUI API
- OpenAI-compatible API

You can still override the provider and model settings in the UI per project, but these environment variables are the default values the backend will use.

#### Ollama

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=
```

Notes:

- Standard local Ollama usually does not require an API key
- If you are exposing Ollama behind a proxy that requires auth, set `OLLAMA_API_KEY`

#### Open WebUI

```env
OPENWEBUI_BASE_URL=http://localhost:3001
OPENWEBUI_API_KEY=your_openwebui_key
```

The backend uses the Open WebUI API endpoints under `/api/...`, so the base URL should be the root of your Open WebUI server.

#### OpenAI-compatible endpoint

```env
OPENAI_COMPATIBLE_BASE_URL=http://localhost:8001
OPENAI_COMPATIBLE_API_KEY=your_api_key
```

The app appends `/v1` internally for the OpenAI-compatible adapter, so use the server root as the base URL unless your deployment requires a different shape.

## Example `.env` setups

### Local Ollama only

```env
HOST=127.0.0.1
PORT=8000
GRAPH_BACKEND=sqlite
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_API_KEY=
```

### Open WebUI only

```env
HOST=127.0.0.1
PORT=8000
GRAPH_BACKEND=sqlite
OPENWEBUI_BASE_URL=http://localhost:3001
OPENWEBUI_API_KEY=your_openwebui_key
```

## Using your own Ollama or Open WebUI instance

After the app starts:

1. Open the UI in the browser
2. In the setup form, choose the provider
3. Set the base URL and API key if needed
4. Test the connection
5. List available models
6. Choose planner, code, and query models
7. Start analysis

For most users:

- Ollama base URL: `http://localhost:11434`
- Open WebUI base URL: `http://localhost:3001`

## Typical workflow

1. Start the application
2. Enter a local path or supported GitHub repository URL
3. Choose language and analysis depth
4. Optionally configure model refinement
5. Run indexing
6. Explore the graph and node details
7. Use graph controls to hide native library and third-party dependency noise

## Notes for publishing this repo

If you are distributing this for other users:

- commit [README.md](README.md)
- commit [LICENSE](LICENSE)
- commit [.env.example](.env.example)
- do not commit a real `.env` with private keys
- tell users to provide their own Ollama or Open WebUI endpoint details

## Author

- Creator: Jagan Jijo
- Portfolio: https://jagan-jijo.github.io/portfolio/

## Troubleshooting

### Backend does not start

- make sure Python 3.11+ is installed
- make sure `.venv` exists or rerun the startup script
- reinstall dependencies with `pip install -r requirements.txt`

### Frontend does not start

- make sure Node.js 18+ is installed
- run `npm install` in the root and in [frontend](frontend)

### Model connection test fails

- verify the base URL is correct
- verify your Ollama or Open WebUI server is already running
- verify the API key if your endpoint requires one

### Graph looks noisy

Use the graph controls to:

- hide inferred edges below the confidence threshold
- hide native / built-in library nodes
- hide third-party dependency nodes
- group functions by module lane

## License

This project is licensed under the custom attribution license in [LICENSE](LICENSE).

Summary:

- free for personal use
- free for commercial use
- you must keep the original credit to Jagan Jijo
- if you redistribute or publish modified versions, the attribution must remain intact

This summary is only a convenience note. The [LICENSE](LICENSE) file is the controlling text.
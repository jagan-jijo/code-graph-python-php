import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))

_projects_dir = os.getenv("PROJECTS_DIR", "").strip()
PROJECTS_DIR: Path = Path(_projects_dir) if _projects_dir else (Path.home() / ".code-graph")
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

GRAPH_BACKEND: str = os.getenv("GRAPH_BACKEND", "sqlite")

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_API_KEY: str = os.getenv("OLLAMA_API_KEY", "")

OPENWEBUI_BASE_URL: str = os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3001")
OPENWEBUI_API_KEY: str = os.getenv("OPENWEBUI_API_KEY", "")

OPENAI_COMPATIBLE_BASE_URL: str = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "http://localhost:8001/v1")
OPENAI_COMPATIBLE_API_KEY: str = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")

MEMGRAPH_HOST: str = os.getenv("MEMGRAPH_HOST", "localhost")
MEMGRAPH_PORT: int = int(os.getenv("MEMGRAPH_PORT", "7687"))

NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB

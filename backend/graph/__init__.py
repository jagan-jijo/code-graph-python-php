from .store import BaseGraphStore
from .inmemory_store import InMemoryGraphStore
from .sqlite_store import SQLiteGraphStore
from config import PROJECTS_DIR


def create_store(backend: str = "sqlite", project_id: str | None = None) -> BaseGraphStore:
    if backend == "sqlite":
        if not project_id:
            raise ValueError("project_id is required for sqlite graph stores")
        return SQLiteGraphStore(str(PROJECTS_DIR / f"{project_id}.sqlite3"))
    if backend == "in_memory":
        return InMemoryGraphStore()
    raise NotImplementedError(f"Graph backend '{backend}' not yet implemented. Use 'sqlite' or 'in_memory'.")


__all__ = ["BaseGraphStore", "InMemoryGraphStore", "SQLiteGraphStore", "create_store"]

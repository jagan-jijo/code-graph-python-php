from __future__ import annotations
import os
import fnmatch
from pathlib import Path
from parsers import get_parser_for_extension, is_dependency_manifest

DEFAULT_EXCLUDES = [
    ".git", ".hg", ".svn", "__pycache__", "*.pyc", "*.pyo",
    "node_modules", ".npm", "vendor", ".tox", ".venv", "venv",
    ".env", "env", "*.egg-info", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
]


def discover_files(root: str, language: str, extra_excludes: list[str] | None = None,
                   max_file_size: int = 5 * 1024 * 1024) -> list[str]:
    root_path = Path(root).resolve()
    excludes = DEFAULT_EXCLUDES + (extra_excludes or [])
    extensions: set[str] = set()
    if language in ("python", "mixed"):
        extensions.add(".py")
    if language in ("php", "mixed"):
        extensions.add(".php")
    if not extensions:
        extensions = {".py", ".php"}
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=True):
        rel_dir = os.path.relpath(dirpath, root_path)
        dirnames[:] = [d for d in dirnames if not _is_excluded(d, rel_dir, excludes)]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in extensions and not is_dependency_manifest(fname):
                continue
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, root_path)
            if _is_excluded(fname, rel_path, excludes):
                continue
            try:
                if os.path.getsize(full_path) > max_file_size:
                    continue
            except OSError:
                continue
            if get_parser_for_extension(ext) is not None or is_dependency_manifest(fname):
                found.append(full_path)
    return found


def _is_excluded(name: str, rel_path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        for part in rel_path.replace("\\", "/").split("/"):
            if fnmatch.fnmatch(part, pattern):
                return True
    return False

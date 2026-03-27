from __future__ import annotations

import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

from .base import ParsedDependency

DEPENDENCY_MANIFESTS = {
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "composer.json",
}


def is_dependency_manifest(file_path: str) -> bool:
    return Path(file_path).name.lower() in DEPENDENCY_MANIFESTS


def parse_dependency_manifest(file_path: str) -> list[ParsedDependency]:
    path = Path(file_path)
    file_name = path.name.lower()
    if file_name == "pyproject.toml":
        return _parse_pyproject(path)
    if file_name == "requirements.txt":
        return _parse_requirements(path)
    if file_name == "package.json":
        return _parse_package_json(path)
    if file_name == "composer.json":
        return _parse_composer_json(path)
    return []


def _parse_pyproject(path: Path) -> list[ParsedDependency]:
    if tomllib is None:
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []

    dependencies: list[ParsedDependency] = []
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    for name, version in poetry_deps.items():
        if str(name).lower() == "python":
            continue
        dependencies.append(ParsedDependency(name=str(name), version=str(version), manifest_path=str(path), ecosystem="python"))

    for entry in data.get("project", {}).get("dependencies", []):
        package = str(entry).split(";", 1)[0].strip()
        name = package.split("[", 1)[0].split(" ", 1)[0].split("=", 1)[0].strip()
        if name:
            dependencies.append(ParsedDependency(name=name, version=package, manifest_path=str(path), ecosystem="python"))

    optional_groups = data.get("project", {}).get("optional-dependencies", {})
    for group_entries in optional_groups.values():
        for entry in group_entries:
            package = str(entry).split(";", 1)[0].strip()
            name = package.split("[", 1)[0].split(" ", 1)[0].split("=", 1)[0].strip()
            if name:
                dependencies.append(ParsedDependency(name=name, version=package, manifest_path=str(path), ecosystem="python"))
    return _dedupe_dependencies(dependencies)


def _parse_requirements(path: Path) -> list[ParsedDependency]:
    dependencies: list[ParsedDependency] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        name = line.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].split("~=", 1)[0].strip()
        if name:
            dependencies.append(ParsedDependency(name=name, version=line, manifest_path=str(path), ecosystem="python"))
    return _dedupe_dependencies(dependencies)


def _parse_package_json(path: Path) -> list[ParsedDependency]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    dependencies: list[ParsedDependency] = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name, version in data.get(section, {}).items():
            dependencies.append(ParsedDependency(name=str(name), version=str(version), manifest_path=str(path), ecosystem="node"))
    return _dedupe_dependencies(dependencies)


def _parse_composer_json(path: Path) -> list[ParsedDependency]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    dependencies: list[ParsedDependency] = []
    for section in ("require", "require-dev"):
        for name, version in data.get(section, {}).items():
            if str(name).lower() == "php":
                continue
            dependencies.append(ParsedDependency(name=str(name), version=str(version), manifest_path=str(path), ecosystem="php"))
    return _dedupe_dependencies(dependencies)


def _dedupe_dependencies(dependencies: list[ParsedDependency]) -> list[ParsedDependency]:
    unique: dict[tuple[str, str | None, str | None], ParsedDependency] = {}
    for dependency in dependencies:
        key = (dependency.name.lower(), dependency.version, dependency.ecosystem)
        unique[key] = dependency
    return list(unique.values())
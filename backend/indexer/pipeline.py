from __future__ import annotations
import asyncio
import builtins
import hashlib
import os
import sys
from typing import Callable, Awaitable, Optional

from parsers import get_parser_for_extension, ParsedFile, parse_dependency_manifest, is_dependency_manifest
from graph.store import BaseGraphStore
from models.graph import GraphNode, GraphEdge, EdgeType, NodeType, Language, ProvenanceTag
from models.project import ProjectConfig, ProgressEvent
from indexer.file_discovery import discover_files
from indexer.python_semantic import build_python_semantic_hints, SemanticReference

ProgressCallback = Callable[[ProgressEvent], Awaitable[None]]

PYTHON_BUILTIN_NAMES = frozenset(dir(builtins))
PYTHON_STDLIB_MODULES = frozenset(getattr(sys, "stdlib_module_names", set()))


class IndexingCancelled(Exception):
    pass


async def run_indexing(project_id: str, root_path: str, language: str,
                       config: ProjectConfig, store: BaseGraphStore,
                       on_progress: Optional[ProgressCallback] = None,
                       should_cancel: Optional[Callable[[], bool]] = None) -> dict:
    async def emit(stage, msg, progress, files_done=0, files_total=0, error=None):
        if on_progress:
            await on_progress(ProgressEvent(
                project_id=project_id, stage=stage, message=msg,
                progress=progress, files_processed=files_done,
                files_total=files_total, error=error,
            ))

    async def check_cancel(stage: str, progress: float, files_done: int = 0, files_total: int = 0):
        if should_cancel and should_cancel():
            await emit(stage, "Analysis stopped.", progress, files_done, files_total)
            raise IndexingCancelled()

    await check_cancel("discovery", 0.0)
    await emit("discovery", "Discovering source files…", 0.02)
    files = discover_files(root_path, language, config.exclude_patterns)
    total = len(files)
    await check_cancel("discovery", 0.05, 0, total)
    await emit("discovery", f"Found {total} files", 0.05, 0, total)
    if total == 0:
        await emit("done", "No files found — check path and language.", 1.0, error="No files found")
        return {"file_count": 0, "node_count": 0, "edge_count": 0}

    current_fingerprints = {file_path: _hash_file(file_path) for file_path in files}
    tracked_files = store.get_tracked_files()
    removed_files = set(tracked_files) - set(current_fingerprints)
    changed_files = {
        file_path for file_path, fingerprint in current_fingerprints.items()
        if store.get_file_fingerprint(file_path) != fingerprint
    }
    impacted_files = set(changed_files)
    for file_path in list(changed_files | removed_files):
        impacted_files.update(store.get_related_files(file_path))

    if not tracked_files:
        store.clear()
        files_to_parse = files
        await emit("discovery", "Initial index detected — parsing all files.", 0.06, 0, total)
    else:
        files_to_parse = [file_path for file_path in files if file_path in impacted_files]
        for file_path in removed_files | impacted_files:
            store.remove_file_records(file_path)
        await emit(
            "discovery",
            f"Incremental index: {len(files_to_parse)} changed/impacted files, {len(removed_files)} removed.",
            0.06,
            0,
            total,
        )

    if not store.get_node(f"repo:{root_path}"):
        repo_node = GraphNode(
            id=f"repo:{root_path}", type=NodeType.REPOSITORY,
            label=os.path.basename(root_path) or root_path,
            language=Language(language) if language in ("python", "php") else Language.MIXED,
            provenance=ProvenanceTag.PARSER_FACT,
        )
        store.add_node(repo_node)

    await emit("parsing", "Parsing files…", 0.1, 0, total)
    parsed_files: list[ParsedFile] = []
    symbol_index, symbol_candidates = _existing_symbol_index(store)
    file_module_map = _existing_file_module_map(store)
    parse_total = max(len(files_to_parse), 1)
    step = 0.7 / parse_total

    for idx, fpath in enumerate(files_to_parse):
        await check_cancel("parsing", 0.1 + step * idx, idx, len(files_to_parse))
        ext = os.path.splitext(fpath)[1].lower()
        parser = get_parser_for_extension(ext)
        if not parser and not is_dependency_manifest(fpath):
            continue
        lang = _language_for_path(fpath)
        if parser:
            pf = parser.parse_file(fpath, root_path)
        else:
            rel = os.path.relpath(fpath, root_path).replace("\\", "/")
            pf = ParsedFile(file_path=fpath, module_name=rel, language=lang.value)
            pf.dependencies = parse_dependency_manifest(fpath)
        parsed_files.append(pf)
        file_module_map[fpath] = pf.module_name
        rel = os.path.relpath(fpath, root_path).replace("\\", "/")
        parent_container_id = _ensure_directory_chain(store, root_path, fpath, lang)
        file_node_id = f"file:{fpath}"
        store.add_node(GraphNode(
            id=file_node_id, type=NodeType.FILE, label=os.path.basename(fpath),
            language=lang, file_path=fpath, qualified_name=pf.module_name,
            provenance=ProvenanceTag.PARSER_FACT,
            properties={"relative_path": rel, "module_name": pf.module_name},
        ))
        store.add_edge(GraphEdge(
            id=f"CONTAINS:{parent_container_id}:{file_node_id}",
            type=EdgeType.CONTAINS, source_id=parent_container_id,
            target_id=file_node_id, language=lang, provenance=ProvenanceTag.PARSER_FACT,
        ))
        module_node_id = f"module:{fpath}"
        store.add_node(GraphNode(
            id=module_node_id,
            type=NodeType.MODULE,
            label=pf.module_name.split(".")[-1] if pf.module_name else os.path.basename(fpath),
            language=lang,
            file_path=fpath,
            qualified_name=pf.module_name,
            provenance=ProvenanceTag.PARSER_FACT,
            properties={"relative_path": rel, "module_name": pf.module_name},
        ))
        store.add_edge(GraphEdge(
            id=f"CONTAINS:{file_node_id}:{module_node_id}",
            type=EdgeType.CONTAINS,
            source_id=file_node_id,
            target_id=module_node_id,
            language=lang,
            provenance=ProvenanceTag.PARSER_FACT,
        ))
        for sym in pf.symbols:
            sym_type = {"function": NodeType.FUNCTION, "method": NodeType.METHOD,
                        "class": NodeType.CLASS, "interface": NodeType.INTERFACE,
                        "trait": NodeType.TRAIT}.get(sym.type, NodeType.FUNCTION)
            store.add_node(GraphNode(
                id=sym.id, type=sym_type, label=sym.name, language=lang,
                file_path=fpath, line_start=sym.line_start, line_end=sym.line_end,
                qualified_name=sym.qualified_name, docstring=sym.docstring,
                signature=sym.signature, decorators=sym.decorators, is_async=sym.is_async,
                provenance=ProvenanceTag.PARSER_FACT,
            ))
            if sym.parent_class:
                parent_id = f"class:{fpath}:{sym.parent_class}"
                container_id = parent_id if store.get_node(parent_id) else module_node_id
            else:
                container_id = module_node_id
            store.add_edge(GraphEdge(
                id=f"CONTAINS:{container_id}:{sym.id}",
                type=EdgeType.CONTAINS, source_id=container_id,
                target_id=sym.id, language=lang, provenance=ProvenanceTag.PARSER_FACT,
            ))
            store.add_edge(GraphEdge(
                id=f"DEFINED_IN:{sym.id}:{file_node_id}",
                type=EdgeType.DEFINED_IN, source_id=sym.id,
                target_id=file_node_id, language=lang, provenance=ProvenanceTag.PARSER_FACT,
            ))
            symbol_index[sym.qualified_name] = sym.id
            symbol_candidates.setdefault(sym.name, []).append(sym.id)
        for dependency in pf.dependencies:
            dependency_node_id = f"dependency:{dependency.ecosystem or 'unknown'}:{dependency.name.lower()}"
            store.add_node(GraphNode(
                id=dependency_node_id,
                type=NodeType.MODULE,
                label=dependency.name,
                language=lang,
                provenance=ProvenanceTag.PARSER_FACT,
                confidence=0.98,
                properties={
                    "external_kind": "third_party",
                    "dependency_manifest": os.path.basename(dependency.manifest_path or fpath),
                    "dependency_name": dependency.name,
                    "dependency_version": dependency.version,
                    "ecosystem": dependency.ecosystem,
                },
            ))
            store.upsert_edge(GraphEdge(
                id=f"DEPENDS_ON:{file_node_id}:{dependency_node_id}",
                type=EdgeType.DEPENDS_ON,
                source_id=file_node_id,
                target_id=dependency_node_id,
                language=lang,
                provenance=ProvenanceTag.PARSER_FACT,
                confidence=0.98,
                evidence=f"dependency manifest: {os.path.basename(dependency.manifest_path or fpath)}",
                file_path=fpath,
            ))
        store.set_file_fingerprint(fpath, current_fingerprints[fpath])
        progress = 0.1 + step * (idx + 1)
        await emit("parsing", f"Parsed {idx+1}/{len(files_to_parse)}: {os.path.basename(fpath)}", progress, idx+1, len(files_to_parse))

    semantic_refs: list[SemanticReference] = []
    semantic_call_map: dict[tuple[str, int, str], list[str]] = {}
    if language in ("python", "mixed") and config.analysis_depth != "fast" and parsed_files:
        await check_cancel("semantic", 0.79)
        await emit("semantic", "Running semantic reference resolution…", 0.79)
        semantic_refs, semantic_call_map = build_python_semantic_hints(root_path, parsed_files)

    await check_cancel("imports", 0.82)
    await emit("imports", "Resolving imports…", 0.82)
    for pf in parsed_files:
        _add_import_edges(pf, store, root_path, file_module_map)

    await check_cancel("calls", 0.88)
    await emit("calls", "Building call graph…", 0.88)
    if config.analysis_depth != "fast":
        for pf in parsed_files:
            _add_call_edges(pf, store, symbol_index, symbol_candidates, semantic_call_map)

    if semantic_refs:
        await check_cancel("references", 0.9)
        await emit("references", "Linking semantic references…", 0.9)
        _add_reference_edges(store, symbol_index, semantic_refs)

    await check_cancel("inheritance", 0.92)
    await emit("inheritance", "Resolving inheritance…", 0.92)
    for pf in parsed_files:
        _add_inheritance_edges(pf, store, symbol_index)

    if config.analysis_depth == "deep":
        await check_cancel("refs", 0.95)
        await emit("refs", "Deep reference resolution…", 0.95)
        _compute_hotspots(store)

    if config.entry_points:
        for ep in config.entry_points:
            for node in store.find_nodes_by_name(ep):
                node.is_entry_point = True
                store.add_node(node)

    await check_cancel("done", 0.99, total, total)
    stats = store.get_stats()
    await emit("done", "Indexing complete.", 1.0, total, total)
    return {"file_count": total, "node_count": stats.node_count, "edge_count": stats.edge_count}


def _hash_file(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _language_for_path(file_path: str) -> Language:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".py" or os.path.basename(file_path).lower() in {"pyproject.toml", "requirements.txt", "package.json"}:
        return Language.PYTHON
    if ext == ".php" or os.path.basename(file_path).lower() == "composer.json":
        return Language.PHP
    return Language.UNKNOWN


def _existing_symbol_index(store: BaseGraphStore) -> tuple[dict[str, str], dict[str, list[str]]]:
    index: dict[str, str] = {}
    candidates: dict[str, list[str]] = {}
    for node in store.get_all_nodes(types=[NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD, NodeType.INTERFACE, NodeType.TRAIT]):
        if node.qualified_name:
            index[node.qualified_name] = node.id
        candidates.setdefault(node.label, []).append(node.id)
    return index, candidates


def _existing_file_module_map(store: BaseGraphStore) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in store.get_all_nodes(types=[NodeType.FILE]):
        if node.file_path and isinstance(node.properties, dict):
            module_name = node.properties.get("module_name")
            if isinstance(module_name, str):
                mapping[node.file_path] = module_name
    return mapping


def _ensure_directory_chain(store: BaseGraphStore, root_path: str, file_path: str, language: Language) -> str:
    relative_dir = os.path.relpath(os.path.dirname(file_path), root_path).replace("\\", "/")
    repo_node_id = f"repo:{root_path}"
    if relative_dir in (".", ""):
        return repo_node_id

    parent_id = repo_node_id
    current_parts: list[str] = []
    for part in [segment for segment in relative_dir.split("/") if segment and segment != "."]:
        current_parts.append(part)
        dir_path = "/".join(current_parts)
        dir_node_id = f"dir:{root_path}:{dir_path}"
        store.add_node(GraphNode(
            id=dir_node_id,
            type=NodeType.DIRECTORY,
            label=part,
            language=language,
            qualified_name=dir_path.replace("/", "."),
            provenance=ProvenanceTag.PARSER_FACT,
            properties={"relative_path": dir_path},
        ))
        store.upsert_edge(GraphEdge(
            id=f"CONTAINS:{parent_id}:{dir_node_id}",
            type=EdgeType.CONTAINS,
            source_id=parent_id,
            target_id=dir_node_id,
            language=language,
            provenance=ProvenanceTag.PARSER_FACT,
        ))
        parent_id = dir_node_id

    return parent_id


def _add_import_edges(pf, store, root_path, file_module_map):
    file_id = f"file:{pf.file_path}"
    lang = Language.PYTHON if pf.language == "python" else Language.PHP
    for imp in pf.imports:
        target_id = None
        for fpath, mod_name in file_module_map.items():
            if mod_name == imp.module or imp.module.startswith(mod_name + "."):
                target_id = f"file:{fpath}"
                break
        if target_id and store.get_node(target_id):
            store.upsert_edge(GraphEdge(
                id=f"IMPORTS:{file_id}:{target_id}",
                type=EdgeType.IMPORTS, source_id=file_id, target_id=target_id,
                language=lang, provenance=ProvenanceTag.REFERENCE_INDEX_FACT,
                evidence=f"{imp.import_type} {imp.module}", line_number=imp.line,
            ))
        else:
            virt_id = f"module:{imp.module}"
            external_kind = _classify_external_module_kind(lang, imp.module)
            if not store.get_node(virt_id):
                store.add_node(GraphNode(
                    id=virt_id, type=NodeType.MODULE, label=imp.module,
                    language=lang, provenance=ProvenanceTag.REFERENCE_INDEX_FACT, confidence=0.8,
                    properties={"external_kind": external_kind, "module_name": imp.module},
                ))
            store.upsert_edge(GraphEdge(
                id=f"USES_MODULE:{file_id}:{virt_id}",
                type=EdgeType.USES_MODULE, source_id=file_id, target_id=virt_id,
                language=lang, provenance=ProvenanceTag.REFERENCE_INDEX_FACT,
                evidence=f"{imp.import_type} {imp.module}", line_number=imp.line,
            ))


def _add_call_edges(pf, store, symbol_index, symbol_candidates, semantic_call_map):
    lang = Language.PYTHON if pf.language == "python" else Language.PHP
    for call in pf.calls:
        if not store.get_node(call.caller_id):
            continue
        target_id = _resolve_call_target(store, pf, call, symbol_index, symbol_candidates, semantic_call_map)
        if target_id:
            edge_type = EdgeType.CALLS
            confidence = 0.92 if semantic_call_map.get((call.caller_id, call.line, call.callee_name)) else 0.9
            prov = ProvenanceTag.REFERENCE_INDEX_FACT
        else:
            virt_id = f"unresolved:{call.callee_name}"
            external_kind = _classify_unresolved_symbol_kind(lang, call.callee_name)
            if not store.get_node(virt_id):
                store.add_node(GraphNode(
                    id=virt_id, type=NodeType.FUNCTION, label=call.callee_name,
                    language=lang, provenance=ProvenanceTag.GRAPH_ALGORITHM_INFERENCE, confidence=0.4,
                    properties={"external_kind": external_kind},
                ))
            target_id = virt_id
            edge_type = EdgeType.POSSIBLE_CALLS
            confidence = 0.4
            prov = ProvenanceTag.GRAPH_ALGORITHM_INFERENCE
        store.upsert_edge(GraphEdge(
            id=f"{edge_type.value}:{call.caller_id}:{target_id}:{call.line}",
            type=edge_type, source_id=call.caller_id, target_id=target_id,
            language=lang, confidence=confidence, provenance=prov, line_number=call.line,
            evidence=f"{'constructor ' if call.is_constructor else ''}call to {call.callee_name}",
        ))


def _resolve_call_target(
    store: BaseGraphStore,
    pf: ParsedFile,
    call,
    symbol_index: dict[str, str],
    symbol_candidates: dict[str, list[str]],
    semantic_call_map: dict[tuple[str, int, str], list[str]],
) -> str | None:
    semantic_candidates = semantic_call_map.get((call.caller_id, call.line, call.callee_name), [])
    for candidate in semantic_candidates:
        target_id = symbol_index.get(candidate)
        if target_id:
            return target_id

    direct_target = symbol_index.get(call.callee_name)
    if direct_target:
        return direct_target

    candidate_ids = list(dict.fromkeys(symbol_candidates.get(call.callee_name, [])))
    if not candidate_ids:
        return None

    source_node = store.get_node(call.caller_id)
    source_qname = source_node.qualified_name if source_node else ""
    source_file = source_node.file_path if source_node else pf.file_path
    source_parts = source_qname.split(".") if source_qname else []
    source_class_prefix = ".".join(source_parts[:-1]) if len(source_parts) > 1 else ""

    if call.object_name == "self" and source_class_prefix:
        for candidate_id in candidate_ids:
            candidate = store.get_node(candidate_id)
            if candidate and candidate.qualified_name and candidate.qualified_name.startswith(f"{source_class_prefix}."):
                return candidate_id

    if call.is_static and call.object_name:
        for candidate_id in candidate_ids:
            candidate = store.get_node(candidate_id)
            if candidate and candidate.qualified_name and call.object_name in candidate.qualified_name:
                return candidate_id

    same_file_candidates = []
    for candidate_id in candidate_ids:
        candidate = store.get_node(candidate_id)
        if candidate and candidate.file_path == source_file:
            same_file_candidates.append(candidate_id)
    if len(same_file_candidates) == 1:
        return same_file_candidates[0]

    if source_parts:
        for index in range(len(source_parts), 0, -1):
            prefix = ".".join(source_parts[:index])
            for candidate_id in candidate_ids:
                candidate = store.get_node(candidate_id)
                if candidate and candidate.qualified_name and candidate.qualified_name.startswith(f"{prefix}."):
                    return candidate_id

    if call.object_name:
        for imported in pf.imports:
            alias_match = imported.alias == call.object_name
            named_match = call.object_name in imported.names
            module_match = imported.module.split(".")[-1] == call.object_name if imported.module else False
            if not alias_match and not named_match and not module_match:
                continue
            for candidate_id in candidate_ids:
                candidate = store.get_node(candidate_id)
                if candidate and candidate.qualified_name and imported.module and imported.module in candidate.qualified_name:
                    return candidate_id

    if len(candidate_ids) == 1:
        return candidate_ids[0]
    return None


def _add_reference_edges(store: BaseGraphStore, symbol_index: dict[str, str], semantic_refs: list[SemanticReference]) -> None:
    for ref in semantic_refs:
        target_id = symbol_index.get(ref.target_qualified_name) or symbol_index.get(ref.target_name)
        if not target_id:
            continue
        source_id = _find_owner_symbol(store, ref.source_file, ref.line) or f"file:{ref.source_file}"
        if not store.get_node(source_id):
            continue
        store.upsert_edge(GraphEdge(
            id=f"REFERENCES:{source_id}:{target_id}:{ref.line}",
            type=EdgeType.REFERENCES,
            source_id=source_id,
            target_id=target_id,
            language=Language.PYTHON,
            confidence=0.88,
            provenance=ProvenanceTag.REFERENCE_INDEX_FACT,
            line_number=ref.line,
            evidence="semantic reference resolution",
            file_path=ref.source_file,
        ))


def _find_owner_symbol(store: BaseGraphStore, file_path: str, line: int) -> str | None:
    best_node_id: str | None = None
    best_span = None
    for node in store.get_all_nodes(types=[NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD, NodeType.INTERFACE, NodeType.TRAIT]):
        if node.file_path != file_path or node.line_start is None or node.line_end is None:
            continue
        if node.line_start <= line <= node.line_end:
            span = node.line_end - node.line_start
            if best_span is None or span < best_span:
                best_span = span
                best_node_id = node.id
    return best_node_id


def _add_inheritance_edges(pf, store, symbol_index):
    lang = Language.PYTHON if pf.language == "python" else Language.PHP
    for sym in pf.symbols:
        if sym.type not in ("class", "interface", "trait") or not sym.bases:
            continue
        for base_name in sym.bases:
            target_id = symbol_index.get(base_name) or symbol_index.get(base_name.split(".")[-1])
            if not target_id:
                virt_id = f"external:{base_name}"
                external_kind = _classify_external_module_kind(lang, base_name)
                if not store.get_node(virt_id):
                    store.add_node(GraphNode(
                        id=virt_id, type=NodeType.CLASS, label=base_name,
                        language=lang, provenance=ProvenanceTag.GRAPH_ALGORITHM_INFERENCE, confidence=0.7,
                        properties={"external_kind": external_kind},
                    ))
                target_id = virt_id
            store.upsert_edge(GraphEdge(
                id=f"EXTENDS:{sym.id}:{target_id}",
                type=EdgeType.EXTENDS, source_id=sym.id, target_id=target_id,
                language=lang, confidence=0.95 if target_id in symbol_index.values() else 0.7,
                provenance=ProvenanceTag.REFERENCE_INDEX_FACT if target_id in symbol_index.values()
                           else ProvenanceTag.GRAPH_ALGORITHM_INFERENCE,
            ))


def _compute_hotspots(store):
    in_degree: dict[str, int] = {}
    for e in store.get_all_edges(types=[EdgeType.CALLS, EdgeType.POSSIBLE_CALLS]):
        in_degree[e.target_id] = in_degree.get(e.target_id, 0) + 1
    max_d = max(in_degree.values(), default=1)
    for node_id, degree in in_degree.items():
        node = store.get_node(node_id)
        if node:
            node.hotspot_score = degree / max_d
            store.add_node(node)


def _classify_external_module_kind(language: Language, name: str) -> str:
    if language != Language.PYTHON:
        return "third_party"
    root_name = name.split(".")[0].strip()
    if not root_name:
        return "third_party"
    if root_name in PYTHON_BUILTIN_NAMES:
        return "builtin"
    if root_name in PYTHON_STDLIB_MODULES:
        return "stdlib"
    return "third_party"


def _classify_unresolved_symbol_kind(language: Language, name: str) -> str:
    if language == Language.PYTHON and name in PYTHON_BUILTIN_NAMES:
        return "builtin"
    return "unknown"

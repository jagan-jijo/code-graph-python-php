from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from parsers.base import ParsedFile, ParsedCall, ParsedSymbol

try:
    import jedi
    _JEDI_AVAILABLE = True
except Exception:
    jedi = None
    _JEDI_AVAILABLE = False


@dataclass
class SemanticReference:
    source_file: str
    line: int
    target_qualified_name: str
    target_name: str


@dataclass
class SemanticCallTarget:
    caller_id: str
    line: int
    callee_name: str
    candidate_names: list[str]


def build_python_semantic_hints(root_path: str, parsed_files: list[ParsedFile]) -> tuple[list[SemanticReference], dict[tuple[str, int, str], list[str]]]:
    if not _JEDI_AVAILABLE:
        return [], {}

    project = jedi.Project(path=root_path)
    references: list[SemanticReference] = []
    call_targets: dict[tuple[str, int, str], list[str]] = {}

    for parsed_file in parsed_files:
        if parsed_file.language != "python":
            continue
        path = Path(parsed_file.file_path)
        try:
            source_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            script = jedi.Script(path=parsed_file.file_path, project=project)
        except Exception:
            continue

        for call in parsed_file.calls:
            targets = _infer_call_targets(script, source_lines, call)
            if targets:
                call_targets[(call.caller_id, call.line, call.callee_name)] = targets

        for symbol in parsed_file.symbols:
            references.extend(_find_references(script, source_lines, root_path, symbol))

    return references, call_targets


def _infer_call_targets(script, source_lines: list[str], call: ParsedCall) -> list[str]:
    if call.line <= 0 or call.line > len(source_lines):
        return []
    line_text = source_lines[call.line - 1]
    column = line_text.find(call.callee_name)
    if column < 0:
        return []
    candidates: list[str] = []
    try:
        for inferred in script.infer(call.line, column):
            full_name = getattr(inferred, "full_name", None)
            if full_name:
                candidates.append(full_name)
            elif inferred.name:
                candidates.append(inferred.name)
    except Exception:
        return []
    return list(dict.fromkeys(candidates))


def _find_references(script, source_lines: list[str], root_path: str, symbol: ParsedSymbol) -> list[SemanticReference]:
    if symbol.line_start <= 0 or symbol.line_start > len(source_lines):
        return []
    line_text = source_lines[symbol.line_start - 1]
    column = line_text.find(symbol.name)
    if column < 0:
        return []
    references: list[SemanticReference] = []
    try:
        names = script.get_references(symbol.line_start, column, include_builtins=False)
    except Exception:
        return []
    for ref in names:
        if getattr(ref, "is_definition", lambda: False)():
            continue
        module_path = getattr(ref, "module_path", None)
        if not module_path:
            continue
        module_path = str(module_path)
        if not module_path.startswith(root_path):
            continue
        references.append(SemanticReference(
            source_file=module_path,
            line=ref.line,
            target_qualified_name=symbol.qualified_name,
            target_name=symbol.name,
        ))
    return references
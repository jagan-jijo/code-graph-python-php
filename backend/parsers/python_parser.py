from __future__ import annotations
import os
import re as _re
from typing import Optional
from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, ParsedCall

try:
    from tree_sitter import Language as _TSLanguage, Parser as _TSParser
    import tree_sitter_python as _tspython
    _py_lang = _TSLanguage(_tspython.language())
    _python_parser = _TSParser(_py_lang)
    _TS_AVAILABLE = True
except Exception:
    _python_parser = None
    _TS_AVAILABLE = False


class PythonParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".py"]

    def parse_file(self, file_path: str, root_path: str) -> ParsedFile:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except Exception as exc:
            return ParsedFile(file_path=file_path, module_name="", language="python", error=str(exc))

        rel = os.path.relpath(file_path, root_path).replace("\\", "/")
        module_name = _path_to_module(rel)
        result = ParsedFile(file_path=file_path, module_name=module_name, language="python")

        if _TS_AVAILABLE and _python_parser is not None:
            _parse_with_treesitter(source, result, module_name)
        else:
            _parse_with_regex(source, result, module_name)
        return result


def _path_to_module(rel: str) -> str:
    if rel.endswith(".py"):
        rel = rel[:-3]
    m = rel.replace("/", ".").replace("\\", ".")
    if m.endswith(".__init__"):
        m = m[:-9]
    return m


def _node_text(node, source: str) -> str:
    return source[node.start_byte:node.end_byte]


def _get_docstring(block_node, source: str) -> Optional[str]:
    for child in block_node.children:
        if child.type == "expression_statement":
            for sc in child.children:
                if sc.type in ("string", "concatenated_string"):
                    raw = _node_text(sc, source)
                    return raw.strip().strip('"""').strip("'''").strip('"').strip("'")
        break
    return None


def _parse_with_treesitter(source: str, result: ParsedFile, module_name: str) -> None:
    tree = _python_parser.parse(source.encode("utf-8"))  # type: ignore[union-attr]
    _visit_node(tree.root_node, result, module_name, source, current_class=None, scope_segments=[])  # type: ignore[arg-type]


def _visit_node(node, result, module_name, source, current_class, scope_segments):
    t = node.type
    if t == "import_statement":
        _extract_import(node, result, source)
    elif t == "import_from_statement":
        _extract_from_import(node, result, source)
    elif t in ("function_definition", "async_function_definition"):
        _extract_function(node, result, module_name, source, current_class, scope_segments, None)
    elif t == "class_definition":
        _extract_class(node, result, module_name, source)
    elif t == "decorated_definition":
        _handle_decorated(node, result, module_name, source, current_class, scope_segments)
    else:
        for child in node.children:
            _visit_node(child, result, module_name, source, current_class, scope_segments)


def _handle_decorated(node, result, module_name, source, current_class, scope_segments):
    decorators = []
    inner = None
    for child in node.children:
        if child.type == "decorator":
            decorators.append(_node_text(child, source).lstrip("@").strip())
        elif child.type in ("function_definition", "async_function_definition"):
            inner = ("func", child)
        elif child.type == "class_definition":
            inner = ("class", child)
    if inner:
        kind, n = inner
        if kind == "func":
            _extract_function(n, result, module_name, source, current_class, scope_segments, decorators)
        else:
            _extract_class(n, result, module_name, source, decorators)


def _extract_function(node, result, module_name, source, current_class, scope_segments, parent_dec):
    name_n = node.child_by_field_name("name")
    if not name_n:
        return
    fname = _node_text(name_n, source)
    is_async = node.type == "async_function_definition"
    qualified_parts = [module_name]
    if current_class:
        qualified_parts.append(current_class)
    qualified_parts.extend(scope_segments)
    qualified_parts.append(fname)
    qname = ".".join(part for part in qualified_parts if part)
    local_parts = ([current_class] if current_class else []) + scope_segments + [fname]
    local_name = ".".join(part for part in local_parts if part)
    if current_class and not scope_segments:
        sym_id = f"method:{result.file_path}:{local_name}"
        sym_type = "method"
    else:
        sym_id = f"func:{result.file_path}:{local_name or fname}"
        sym_type = "function"
    params = _extract_params(node, source)
    body = node.child_by_field_name("body")
    doc = _get_docstring(body, source) if body else None
    sig = f"{'async ' if is_async else ''}def {fname}({', '.join(params)})"
    result.symbols.append(ParsedSymbol(
        id=sym_id, type=sym_type, name=fname, qualified_name=qname,
        file_path=result.file_path, line_start=node.start_point[0]+1, line_end=node.end_point[0]+1,
        parent_class=current_class, docstring=doc, signature=sig,
        parameters=params, decorators=parent_dec or [], is_async=is_async,
    ))
    if body:
        _extract_calls_recursive(body, result, sym_id, source)
        for child in body.children:
            _visit_node(child, result, module_name, source, current_class, [*scope_segments, fname])


def _extract_params(func_node, source):
    params_node = func_node.child_by_field_name("parameters")
    if not params_node:
        return []
    params = []
    for child in params_node.children:
        if child.type == "identifier":
            params.append(_node_text(child, source))
        elif child.type in ("typed_parameter", "default_parameter",
                             "typed_default_parameter", "list_splat_pattern",
                             "dictionary_splat_pattern"):
            for sc in child.children:
                if sc.type == "identifier":
                    params.append(_node_text(sc, source))
                    break
    return [p for p in params if p not in ("(", ")", ",")]


def _extract_class(node, result, module_name, source, decorators=None):
    name_n = node.child_by_field_name("name")
    if not name_n:
        return
    cname = _node_text(name_n, source)
    sym_id = f"class:{result.file_path}:{cname}"
    qname = f"{module_name}.{cname}"
    bases = []
    sc_node = node.child_by_field_name("superclasses") or node.child_by_field_name("bases")
    if sc_node:
        for child in sc_node.children:
            if child.type in ("identifier", "attribute", "dotted_name"):
                bases.append(_node_text(child, source))
    body = node.child_by_field_name("body")
    doc = _get_docstring(body, source) if body else None
    result.symbols.append(ParsedSymbol(
        id=sym_id, type="class", name=cname, qualified_name=qname,
        file_path=result.file_path, line_start=node.start_point[0]+1, line_end=node.end_point[0]+1,
        docstring=doc, decorators=decorators or [], bases=bases,
    ))
    if body:
        for child in body.children:
            if child.type in ("function_definition", "async_function_definition"):
                _extract_function(child, result, module_name, source, cname, None)
            elif child.type == "decorated_definition":
                _handle_decorated_class(child, result, module_name, source, cname)
            elif child.type == "class_definition":
                _extract_class(child, result, module_name, source)


def _handle_decorated_class(node, result, module_name, source, class_name):
    decs = []
    for child in node.children:
        if child.type == "decorator":
            decs.append(_node_text(child, source).lstrip("@").strip())
        elif child.type in ("function_definition", "async_function_definition"):
            _extract_function(child, result, module_name, source, class_name, decs)
        elif child.type == "class_definition":
            _extract_class(child, result, module_name, source, decs)


def _extract_import(node, result, source):
    for child in node.children:
        if child.type == "dotted_name":
            result.imports.append(ParsedImport(
                file_path=result.file_path, import_type="import",
                module=_node_text(child, source), names=[], line=node.start_point[0]+1,
            ))
        elif child.type == "aliased_import":
            n = child.child_by_field_name("name")
            a = child.child_by_field_name("alias")
            if n:
                result.imports.append(ParsedImport(
                    file_path=result.file_path, import_type="import",
                    module=_node_text(n, source), names=[],
                    alias=_node_text(a, source) if a else None,
                    line=node.start_point[0]+1,
                ))


def _extract_from_import(node, result, source):
    level = 0
    module = ""
    names: list[str] = []
    for child in node.children:
        if child.type == "relative_import":
            for sc in child.children:
                if sc.type == "import_prefix":
                    level = _node_text(sc, source).count(".")
                elif sc.type == "dotted_name":
                    module = _node_text(sc, source)
        elif child.type == "dotted_name":
            if not module:
                module = _node_text(child, source)
        elif child.type in ("import_as_names", "import_as_name"):
            for sc in child.children:
                if sc.type == "identifier":
                    names.append(_node_text(sc, source))
        elif child.type == "identifier":
            names.append(_node_text(child, source))
        elif child.type == "wildcard_import":
            names.append("*")
    if module or level > 0:
        result.imports.append(ParsedImport(
            file_path=result.file_path, import_type="from",
            module=module, names=names, is_relative=level > 0, level=level,
            line=node.start_point[0]+1,
        ))


def _extract_calls_recursive(node, result, caller_id, source):
    if node.type == "call":
        fn = node.child_by_field_name("function")
        if fn:
            if fn.type == "identifier":
                callee = _node_text(fn, source)
                result.calls.append(ParsedCall(
                    file_path=result.file_path, caller_id=caller_id,
                    callee_name=callee, line=node.start_point[0]+1,
                    is_constructor=bool(callee and callee[0].isupper()),
                ))
            elif fn.type == "attribute":
                obj_n = fn.child_by_field_name("object")
                attr_n = fn.child_by_field_name("attribute")
                if attr_n:
                    result.calls.append(ParsedCall(
                        file_path=result.file_path, caller_id=caller_id,
                        callee_name=_node_text(attr_n, source),
                        object_name=_node_text(obj_n, source) if obj_n else None,
                        line=node.start_point[0]+1,
                    ))
    for child in node.children:
        _extract_calls_recursive(child, result, caller_id, source)


# ── regex fallback ────────────────────────────────────────────────

_RX_FUNC = _re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)\s*:")
_RX_CLASS = _re.compile(r"^(\s*)class\s+(\w+)\s*(?:\(([^)]*)\))?:")
_RX_IMPORT = _re.compile(r"^(?:import\s+(\S+)|from\s+(\S+)\s+import\s+(.+))$")


def _parse_with_regex(source: str, result: ParsedFile, module_name: str) -> None:
    class_stack: list[tuple[str, int]] = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        while class_stack and indent <= class_stack[-1][1]:
            class_stack.pop()
        current_class = class_stack[-1][0] if class_stack else None
        m = _RX_CLASS.match(line)
        if m:
            cname = m.group(2)
            bases_str = m.group(3) or ""
            bases = [b.strip() for b in bases_str.split(",") if b.strip()]
            result.symbols.append(ParsedSymbol(
                id=f"class:{result.file_path}:{cname}", type="class", name=cname,
                qualified_name=f"{module_name}.{cname}",
                file_path=result.file_path, line_start=i, line_end=i, bases=bases,
            ))
            class_stack.append((cname, indent))
            continue
        m = _RX_FUNC.match(line)
        if m:
            fname = m.group(2)
            params = [p.split(":")[0].split("=")[0].strip() for p in m.group(3).split(",") if p.strip()]
            if current_class:
                sym_id = f"method:{result.file_path}:{current_class}.{fname}"
                qname = f"{module_name}.{current_class}.{fname}"
                sym_type = "method"
            else:
                sym_id = f"func:{result.file_path}:{fname}"
                qname = f"{module_name}.{fname}"
                sym_type = "function"
            result.symbols.append(ParsedSymbol(
                id=sym_id, type=sym_type, name=fname, qualified_name=qname,
                file_path=result.file_path, line_start=i, line_end=i,
                parameters=params, parent_class=current_class,
            ))
            continue
        m = _RX_IMPORT.match(stripped)
        if m:
            if m.group(1):
                result.imports.append(ParsedImport(file_path=result.file_path, import_type="import",
                    module=m.group(1), names=[], line=i))
            else:
                result.imports.append(ParsedImport(file_path=result.file_path, import_type="from",
                    module=m.group(2) or "", names=[n.strip() for n in m.group(3).split(",")], line=i))

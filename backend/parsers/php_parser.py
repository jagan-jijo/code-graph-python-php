from __future__ import annotations
import os
import re as _re
from typing import Optional
from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, ParsedCall

try:
    from tree_sitter import Language as _TSLanguage, Parser as _TSParser
    import tree_sitter_php as _tsphp
    _lang_fn = getattr(_tsphp, "language_php", None) or getattr(_tsphp, "language", None)
    _php_lang = _TSLanguage(_lang_fn())
    _php_parser = _TSParser(_php_lang)
    _TS_AVAILABLE = True
except Exception:
    _php_parser = None
    _TS_AVAILABLE = False


class PhpParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".php"]

    def parse_file(self, file_path: str, root_path: str) -> ParsedFile:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except Exception as exc:
            return ParsedFile(file_path=file_path, module_name="", language="php", error=str(exc))
        rel = os.path.relpath(file_path, root_path).replace("\\", "/")
        module_name = rel[:-4] if rel.endswith(".php") else rel
        module_name = module_name.replace("/", "\\")
        result = ParsedFile(file_path=file_path, module_name=module_name, language="php")
        if _TS_AVAILABLE and _php_parser is not None:
            try:
                _parse_with_treesitter(source, result, module_name)
            except Exception:
                _parse_with_regex(source, result, module_name)
        else:
            _parse_with_regex(source, result, module_name)
        return result


def _node_text(node, source: str) -> str:
    return source[node.start_byte:node.end_byte]


def _parse_with_treesitter(source, result, default_module):
    tree = _php_parser.parse(source.encode("utf-8"))  # type: ignore[union-attr]
    _visit_php(tree.root_node, result, default_module, source, None)


def _visit_php(node, result, namespace, source, current_class):
    t = node.type
    if t == "namespace_definition":
        n = node.child_by_field_name("name")
        if n:
            namespace = _node_text(n, source)
        for child in node.children:
            _visit_php(child, result, namespace, source, current_class)
    elif t == "namespace_use_declaration":
        _extract_use(node, result, source)
    elif t == "function_definition":
        _extract_php_function(node, result, namespace, source, current_class)
    elif t in ("class_declaration", "interface_declaration", "trait_declaration"):
        kind = t.replace("_declaration", "")
        _extract_php_class(node, result, namespace, source, kind)
    elif t in ("include_expression", "include_once_expression",
               "require_expression", "require_once_expression"):
        for child in node.children:
            if child.type in ("string", "encapsed_string"):
                val = _node_text(child, source).strip("'\"")
                result.imports.append(ParsedImport(
                    file_path=result.file_path, import_type="include",
                    module=val, names=[], line=node.start_point[0]+1,
                ))
    else:
        for child in node.children:
            _visit_php(child, result, namespace, source, current_class)


def _extract_use(node, result, source):
    line = node.start_point[0]+1
    for child in node.children:
        if child.type == "namespace_use_clause":
            n = child.child_by_field_name("name")
            a = child.child_by_field_name("alias")
            if n:
                module_name = _node_text(n, source)
                result.imports.append(ParsedImport(
                    file_path=result.file_path, import_type="use",
                    module=module_name, names=[module_name.split("\\")[-1]],
                    alias=_node_text(a, source) if a else None, line=line,
                ))


def _extract_php_function(node, result, namespace, source, current_class):
    name_n = node.child_by_field_name("name")
    if not name_n:
        return
    fname = _node_text(name_n, source)
    if current_class:
        sym_id = f"method:{result.file_path}:{current_class}.{fname}"
        qname = f"{namespace}\\{current_class}::{fname}"
        sym_type = "method"
    else:
        sym_id = f"func:{result.file_path}:{fname}"
        qname = f"{namespace}\\{fname}"
        sym_type = "function"
    params = []
    params_n = node.child_by_field_name("parameters")
    if params_n:
        for child in params_n.children:
            if child.type == "simple_parameter":
                pn = child.child_by_field_name("name")
                if pn:
                    params.append(_node_text(pn, source).lstrip("$"))
    result.symbols.append(ParsedSymbol(
        id=sym_id, type=sym_type, name=fname, qualified_name=qname,
        file_path=result.file_path, line_start=node.start_point[0]+1,
        line_end=node.end_point[0]+1, parameters=params, parent_class=current_class,
    ))
    body_n = node.child_by_field_name("body")
    if body_n:
        _extract_php_calls(body_n, result, sym_id, source)


def _extract_php_class(node, result, namespace, source, kind):
    name_n = node.child_by_field_name("name")
    if not name_n:
        return
    cname = _node_text(name_n, source)
    sym_id = f"class:{result.file_path}:{cname}"
    qname = f"{namespace}\\{cname}"
    bases = _extract_php_bases(node, source)
    result.symbols.append(ParsedSymbol(
        id=sym_id, type=kind, name=cname, qualified_name=qname,
        file_path=result.file_path, line_start=node.start_point[0]+1,
        line_end=node.end_point[0]+1, bases=bases,
    ))
    body_n = node.child_by_field_name("body")
    if body_n:
        for child in body_n.children:
            if child.type in ("method_declaration", "function_definition"):
                _extract_php_function(child, result, namespace, source, cname)


def _extract_php_calls(node, result, caller_id, source):
    t = node.type
    if t == "function_call_expression":
        fn = node.child_by_field_name("function")
        if fn and fn.type in ("name", "qualified_name"):
            result.calls.append(ParsedCall(
                file_path=result.file_path, caller_id=caller_id,
                callee_name=_node_text(fn, source), line=node.start_point[0]+1,
            ))
    elif t == "member_call_expression":
        obj_n = node.child_by_field_name("object")
        name_n = node.child_by_field_name("name")
        if name_n:
            result.calls.append(ParsedCall(
                file_path=result.file_path, caller_id=caller_id,
                callee_name=_node_text(name_n, source),
                object_name=_node_text(obj_n, source) if obj_n else None,
                line=node.start_point[0]+1,
            ))
    elif t in ("scoped_call_expression", "static_call_expression"):
        scope_n = node.child_by_field_name("scope") or node.child_by_field_name("class")
        name_n = node.child_by_field_name("name") or node.child_by_field_name("member")
        if name_n:
            result.calls.append(ParsedCall(
                file_path=result.file_path,
                caller_id=caller_id,
                callee_name=_node_text(name_n, source),
                object_name=_node_text(scope_n, source) if scope_n else None,
                line=node.start_point[0]+1,
                is_static=True,
            ))
    elif t == "object_creation_expression":
        cls_n = node.child_by_field_name("class_name") or node.child_by_field_name("class")
        if cls_n:
            result.calls.append(ParsedCall(
                file_path=result.file_path, caller_id=caller_id,
                callee_name=_node_text(cls_n, source),
                is_constructor=True, line=node.start_point[0]+1,
            ))
    for child in node.children:
        _extract_php_calls(child, result, caller_id, source)


def _extract_php_bases(node, source: str) -> list[str]:
    bases: list[str] = []
    header = source[node.start_byte:min(node.end_byte, node.start_byte + 300)]
    match = _re.search(r"\bextends\s+([\\\w]+)", header)
    if match:
        bases.append(match.group(1))
    impl_match = _re.search(r"\bimplements\s+([^\{]+)", header)
    if impl_match:
        for part in impl_match.group(1).split(","):
            name = part.strip()
            if name:
                bases.append(name)
    return bases


# ── regex fallback ────────────────────────────────────────────────

_RX_NS = _re.compile(r"^\s*namespace\s+([\w\\]+)\s*;")
_RX_USE = _re.compile(r"^\s*use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;")
_RX_CLASS = _re.compile(r"^\s*(?:abstract\s+)?class\s+(\w+)")
_RX_IFACE = _re.compile(r"^\s*interface\s+(\w+)")
_RX_TRAIT = _re.compile(r"^\s*trait\s+(\w+)")
_RX_FUNC = _re.compile(r"^\s*(?:public|protected|private|static|abstract|final|\s)*function\s+(\w+)\s*\(([^)]*)\)")
_RX_INCLUDE = _re.compile(r"\b(?:include|require)(?:_once)?\s+['\"]([^'\"]+)['\"]")
_RX_EXTENDS = _re.compile(r"\bextends\s+([\\\w]+)")
_RX_IMPLEMENTS = _re.compile(r"\bimplements\s+([^\{]+)")


def _parse_with_regex(source, result, module_name):
    namespace = module_name
    current_class: Optional[str] = None
    for i, line in enumerate(source.splitlines(), 1):
        m = _RX_NS.match(line)
        if m:
            namespace = m.group(1)
            continue
        m = _RX_USE.match(line)
        if m:
            result.imports.append(ParsedImport(file_path=result.file_path, import_type="use",
                module=m.group(1), names=[], alias=m.group(2), line=i))
            continue
        for rx, kind in ((_RX_CLASS, "class"), (_RX_IFACE, "interface"), (_RX_TRAIT, "trait")):
            m = rx.match(line)
            if m:
                current_class = m.group(1)
                bases: list[str] = []
                ext_match = _RX_EXTENDS.search(line)
                if ext_match:
                    bases.append(ext_match.group(1))
                impl_match = _RX_IMPLEMENTS.search(line)
                if impl_match:
                    bases.extend([part.strip() for part in impl_match.group(1).split(",") if part.strip()])
                result.symbols.append(ParsedSymbol(
                    id=f"class:{result.file_path}:{current_class}", type=kind,
                    name=current_class, qualified_name=f"{namespace}\\{current_class}",
                    file_path=result.file_path, line_start=i, line_end=i,
                    bases=bases,
                ))
                break
        m = _RX_FUNC.match(line)
        if m:
            fname = m.group(1)
            params = [p.strip().lstrip("$") for p in m.group(2).split(",") if p.strip()]
            if current_class:
                sym_id = f"method:{result.file_path}:{current_class}.{fname}"
                qname = f"{namespace}\\{current_class}::{fname}"
                sym_type = "method"
            else:
                sym_id = f"func:{result.file_path}:{fname}"
                qname = f"{namespace}\\{fname}"
                sym_type = "function"
            result.symbols.append(ParsedSymbol(
                id=sym_id, type=sym_type, name=fname, qualified_name=qname,
                file_path=result.file_path, line_start=i, line_end=i,
                parameters=params, parent_class=current_class,
            ))
        for m2 in _RX_INCLUDE.finditer(line):
            result.imports.append(ParsedImport(file_path=result.file_path, import_type="include",
                module=m2.group(1), names=[], line=i))

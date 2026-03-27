from .python_parser import PythonParser
from .php_parser import PhpParser
from .base import BaseParser, ParsedFile, ParsedSymbol, ParsedImport, ParsedCall, ParsedDependency
from .dependency_parser import is_dependency_manifest, parse_dependency_manifest

_PARSERS: list[BaseParser] = [PythonParser(), PhpParser()]
_EXT_MAP: dict[str, BaseParser] = {}
for _p in _PARSERS:
    for _ext in _p.supported_extensions():
        _EXT_MAP[_ext] = _p


def get_parser_for_extension(ext: str) -> BaseParser | None:
    return _EXT_MAP.get(ext.lower())


__all__ = [
    "PythonParser", "PhpParser", "BaseParser",
    "ParsedFile", "ParsedSymbol", "ParsedImport", "ParsedCall", "ParsedDependency",
    "get_parser_for_extension",
    "is_dependency_manifest", "parse_dependency_manifest",
]

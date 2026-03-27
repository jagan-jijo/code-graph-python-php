from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedSymbol:
    id: str
    type: str
    name: str
    qualified_name: str
    file_path: str
    line_start: int
    line_end: int
    parent_class: Optional[str] = None
    docstring: Optional[str] = None
    signature: Optional[str] = None
    parameters: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False
    bases: list[str] = field(default_factory=list)


@dataclass
class ParsedImport:
    file_path: str
    import_type: str
    module: str
    names: list[str]
    alias: Optional[str] = None
    is_relative: bool = False
    level: int = 0
    line: int = 0


@dataclass
class ParsedCall:
    file_path: str
    caller_id: str
    callee_name: str
    object_name: Optional[str] = None
    line: int = 0
    is_constructor: bool = False
    is_static: bool = False


@dataclass
class ParsedDependency:
    name: str
    version: Optional[str] = None
    manifest_path: Optional[str] = None
    ecosystem: Optional[str] = None


@dataclass
class ParsedFile:
    file_path: str
    module_name: str
    language: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)
    dependencies: list[ParsedDependency] = field(default_factory=list)
    error: Optional[str] = None


class BaseParser(ABC):
    @abstractmethod
    def supported_extensions(self) -> list[str]: ...

    @abstractmethod
    def parse_file(self, file_path: str, root_path: str) -> ParsedFile: ...

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CallDirection = Literal["callers", "callees"]
IncludeDirection = Literal["includes", "included_by"]


class IndexInfo(BaseModel):
    """Attached to every report (I3): a stale/absent index is signalled, never silent (I4)."""

    stale: bool = False
    warning: str | None = None


class Location(BaseModel):
    """A source position. `line`/`column` are 1-based (C5), `file` is workspace-relative (C7)."""

    file: str
    line: int
    column: int


class CodeSnippet(BaseModel):
    """A bounded excerpt (C6): never a whole file, always `context_lines` around the match."""

    file: str
    start_line: int
    end_line: int
    text: str


class SymbolMatch(BaseModel):
    name: str
    kind: str
    container: str | None = None
    location: Location
    detail: str | None = None


class FindSymbolRequest(BaseModel):
    query: str
    max_results: int = 20


class FindSymbolReport(BaseModel):
    ok: bool
    matches: list[SymbolMatch] = Field(default_factory=list)
    truncated: int = 0
    index: IndexInfo = Field(default_factory=IndexInfo)


class DefinitionRequest(BaseModel):
    file: str
    line: int
    column: int
    include_body: bool = False
    context_lines: int = 0


class DefinitionReport(BaseModel):
    """C2: signature + doc by default. `body` is populated only if `include_body=True`."""

    ok: bool
    location: Location | None = None
    signature: str | None = None
    documentation: str | None = None
    body: CodeSnippet | None = None
    index: IndexInfo = Field(default_factory=IndexInfo)


class ReferencesRequest(BaseModel):
    file: str
    line: int
    column: int
    max_results: int = 200


class ReferenceHit(BaseModel):
    location: Location
    container: str | None = None


class ReferencesReport(BaseModel):
    ok: bool
    references: list[ReferenceHit] = Field(default_factory=list)
    total_found: int = 0
    truncated: int = 0
    index: IndexInfo = Field(default_factory=IndexInfo)


class ImplementationsRequest(BaseModel):
    file: str
    line: int
    column: int
    max_results: int = 100


class ImplementationsReport(BaseModel):
    ok: bool
    implementations: list[SymbolMatch] = Field(default_factory=list)
    truncated: int = 0
    index: IndexInfo = Field(default_factory=IndexInfo)


class OutlineRequest(BaseModel):
    file: str


class OutlineSymbol(BaseModel):
    """No function/method body ever appears here (C1) — structure and signatures only."""

    name: str
    kind: str
    detail: str | None = None
    start_line: int
    end_line: int
    children: list[OutlineSymbol] = Field(default_factory=list)


class OutlineReport(BaseModel):
    ok: bool
    file: str
    symbols: list[OutlineSymbol] = Field(default_factory=list)
    index: IndexInfo = Field(default_factory=IndexInfo)


class SignatureRequest(BaseModel):
    file: str
    line: int
    column: int


class SignatureReport(BaseModel):
    ok: bool
    signature: str | None = None
    documentation: str | None = None
    index: IndexInfo = Field(default_factory=IndexInfo)


class CallGraphRequest(BaseModel):
    file: str
    line: int
    column: int
    direction: CallDirection
    max_depth: int = 2
    max_results: int = 100


class CallGraphNode(BaseModel):
    name: str
    location: Location
    children: list[CallGraphNode] = Field(default_factory=list)


class CallGraphReport(BaseModel):
    ok: bool
    root: CallGraphNode | None = None
    truncated: int = 0
    index: IndexInfo = Field(default_factory=IndexInfo)


class IncludesRequest(BaseModel):
    file: str
    direction: IncludeDirection
    max_depth: int = 1
    max_results: int = 200


class IncludesReport(BaseModel):
    ok: bool
    file: str
    direction: IncludeDirection
    edges: list[str] = Field(default_factory=list)
    truncated: int = 0


class GrepRequest(BaseModel):
    pattern: str
    paths: list[str] = Field(default_factory=lambda: ["."])
    exclude_comments: bool = True
    exclude_strings: bool = True
    context_lines: int = 0
    max_results: int = 100
    is_regexp: bool = False


class GrepMatch(BaseModel):
    file: str
    line: int
    text: str
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class GrepReport(BaseModel):
    ok: bool
    matches: list[GrepMatch] = Field(default_factory=list)
    truncated: int = 0


class RegistryMatrixRequest(BaseModel):
    paths: list[str] = Field(default_factory=lambda: ["."])
    max_results: int = 500


class RegistryEntry(BaseModel):
    instrument: str
    model: str
    engine: str
    adapter: str


class RegistryCombination(BaseModel):
    instrument: str
    model: str
    engine: str


class RegistryMatrixReport(BaseModel):
    ok: bool
    entries: list[RegistryEntry] = Field(default_factory=list)
    missing_combinations: list[RegistryCombination] = Field(default_factory=list)
    truncated: int = 0
    index: IndexInfo = Field(default_factory=IndexInfo)


class DiffContextRequest(BaseModel):
    base_ref: str
    head_ref: str = "HEAD"
    max_results: int = 50


class ImpactedSymbol(BaseModel):
    name: str
    location: Location
    references_count: int


class DiffContextReport(BaseModel):
    ok: bool
    impacted: list[ImpactedSymbol] = Field(default_factory=list)
    truncated: int = 0
    index: IndexInfo = Field(default_factory=IndexInfo)

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.rag import EvidenceItem


class ArchitectureTraceRequest(BaseModel):
    """Request payload for deterministic architecture trace."""

    start_symbol: str = Field(
        ...,
        min_length=1,
        description="Exact qualified name of the start symbol (e.g. orders.service.OrderService.create_order)",
    )
    max_depth: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Maximum traversal call-depth (default: system setting)",
    )
    max_nodes: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Maximum total symbols to traverse (default: system setting)",
    )


class ArchitectureTraceNode(BaseModel):
    """A node in the architecture execution trace."""

    step: int = Field(..., description="1-indexed execution discovery step")
    qualified_name: str = Field(..., description="Fully qualified symbol name")
    name: str = Field(..., description="Short symbol name")
    symbol_type: str = Field(..., description="Type of symbol (e.g. function, method, class)")
    file: str = Field(..., description="Relative file path where the symbol is defined")
    line_start: int | None = Field(default=None, description="Starting line in source file")
    line_end: int | None = Field(default=None, description="Ending line in source file")
    signature: str | None = Field(default=None, description="Function/method signature if available")

    model_config = ConfigDict(from_attributes=True)


class ArchitectureTraceEdge(BaseModel):
    """A directed call relationship edge in the execution trace."""

    model_config = ConfigDict(populate_by_name=True)

    from_symbol: str = Field(
        ...,
        alias="from",
        serialization_alias="from",
        description="Qualified name of caller symbol",
    )
    to_symbol: str = Field(
        ...,
        alias="to",
        serialization_alias="to",
        description="Qualified name of callee symbol",
    )
    relationship: str = Field(
        default="calls",
        description="Relationship type (always 'calls')",
    )
    source_line: int | None = Field(
        default=None,
        description="Line number in source file where the call occurs",
    )


class ArchitectureTraceResponse(BaseModel):
    """Complete architecture trace response containing nodes, edges, and deterministic summary."""

    start_symbol: str = Field(..., description="Starting qualified symbol name")
    nodes: list[ArchitectureTraceNode] = Field(
        default_factory=list,
        description="Deterministic list of traversed symbols",
    )
    edges: list[ArchitectureTraceEdge] = Field(
        default_factory=list,
        description="Directed call relationship edges",
    )
    summary: str = Field(
        ...,
        description="Deterministic summary derived purely from graph traversal",
    )

    model_config = ConfigDict(populate_by_name=True)


class ArchitectureExplainRequest(BaseModel):
    """Request payload for architecture-aware RAG question answering."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question about the codebase architecture or execution flow",
    )


class ArchitectureExplainTrace(BaseModel):
    """Architecture trace graph included in architecture explanation."""

    start_symbol: str = Field(..., description="Starting qualified symbol name")
    nodes: list[ArchitectureTraceNode] = Field(
        default_factory=list,
        description="Deterministic list of traversed symbols",
    )
    edges: list[ArchitectureTraceEdge] = Field(
        default_factory=list,
        description="Directed call relationship edges",
    )

    model_config = ConfigDict(populate_by_name=True)


class ArchitectureExplainResponse(BaseModel):
    """Complete architecture-aware RAG response containing answer, trace, and evidence."""

    question: str = Field(..., description="User's original question")
    answer: str = Field(..., description="AI generated grounded architecture explanation")
    trace: ArchitectureExplainTrace | None = Field(
        default=None,
        description="Deterministic static architecture call trace",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Code evidence items cited in the answer",
    )

    model_config = ConfigDict(populate_by_name=True)

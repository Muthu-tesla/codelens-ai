from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    """Request model for evidence-grounded AI codebase question answering."""
    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question about the codebase",
    )


class EvidenceItem(BaseModel):
    """Individual code evidence unit supporting an AI answer."""
    id: str = Field(..., description="Deterministic evidence identifier, e.g. E1, E2")
    file: str = Field(..., description="Source code relative file path")
    qualified_name: str | None = Field(default=None, description="Symbol or module qualified name")
    symbol_type: str | None = Field(default=None, description="Symbol type: function, method, class, module")
    line_start: int | None = Field(default=None, description="Starting line in source file")
    line_end: int | None = Field(default=None, description="Ending line in source file")
    content: str = Field(..., description="Source code slice or chunk content")
    similarity: float | None = Field(default=None, description="Retrieval similarity score if available")


class AskResponse(BaseModel):
    """Response model containing grounded answer and verified code evidence."""
    answer: str = Field(..., description="AI generated answer citing evidence markers like [E1]")
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="List of verified code evidence snippets cited in the answer",
    )

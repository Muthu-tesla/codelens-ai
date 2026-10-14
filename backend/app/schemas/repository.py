from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class RepositoryCreate(BaseModel):
    """Schema for registering a repository."""
    name: str = Field(..., min_length=1, max_length=255, description="Repository identifier name")
    path: str = Field(..., min_length=1, description="Absolute or relative local path to the repository directory")


class RepositoryResponse(BaseModel):
    """Schema for repository details response."""
    id: int
    name: str
    path: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileMetadata(BaseModel):
    """Schema for discovered repository file metadata."""
    relative_path: str = Field(..., description="Path relative to the repository root")
    extension: str = Field(..., description="File extension including leading dot")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    line_count: int = Field(..., ge=0, description="Total number of lines in file")


class RepositoryFilesResponse(BaseModel):
    """Schema for list of discovered files."""
    repository_id: int
    total_files: int
    files: list[FileMetadata]


class RepositoryAnalysisSummary(BaseModel):
    """Schema for repository code analysis summary."""
    repository_id: int
    files_analyzed: int
    python_files: int
    classes: int
    functions: int
    methods: int = 0
    imports: int = 0
    relationships: int = 0
    call_relationships: int = 0
    chunks_created: int = 0
    embeddings_generated: int = 0
    errors: list[str] = Field(default_factory=list, description="Non-fatal warnings or parse errors encountered during analysis")


class CodeSymbolBrief(BaseModel):
    """Brief representation of a code symbol for relationship edges."""
    id: int
    name: str
    qualified_name: str
    symbol_type: str

    model_config = ConfigDict(from_attributes=True)


class CodeSymbolResponse(BaseModel):
    """Schema for code symbol list response."""
    id: int
    file_id: int
    relative_path: str | None = None
    qualified_name: str
    name: str
    symbol_type: str
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CodeRelationshipResponse(BaseModel):
    """Schema for a code relationship edge."""
    id: int
    repository_id: int
    relationship_type: str
    source_line: int | None = None
    source_symbol: CodeSymbolBrief
    target_symbol: CodeSymbolBrief
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CodeSymbolDetailResponse(BaseModel):
    """Detailed schema for a code symbol, including its relationships."""
    id: int
    file_id: int
    relative_path: str
    qualified_name: str
    name: str
    symbol_type: str
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    created_at: datetime
    outgoing_relationships: list[CodeRelationshipResponse] = Field(default_factory=list)
    incoming_relationships: list[CodeRelationshipResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SemanticSearchRequest(BaseModel):
    """Request schema for semantic code similarity search."""
    query: str = Field(..., min_length=1, description="Natural language or code query string")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum number of chunks to return")


class SearchResultItem(BaseModel):
    """Individual search result item representing a matching code chunk."""
    chunk_id: int
    file: str
    qualified_name: str | None = None
    chunk_type: str
    line_start: int | None = None
    line_end: int | None = None
    similarity: float
    content: str


class SemanticSearchResponse(BaseModel):
    """Response schema for semantic code similarity search."""
    query: str
    results: list[SearchResultItem]

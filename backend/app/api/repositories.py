from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.repository import (
    CodeRelationshipResponse,
    CodeSymbolDetailResponse,
    CodeSymbolResponse,
    RepositoryAnalysisSummary,
    RepositoryCreate,
    RepositoryFilesResponse,
    RepositoryResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.schemas.rag import AskResponse, QuestionRequest
from app.schemas.architecture import (
    ArchitectureExplainRequest,
    ArchitectureExplainResponse,
    ArchitectureTraceRequest,
    ArchitectureTraceResponse,
)
from app.services.architecture.explain_service import architecture_explain_service
from app.services.architecture.trace_service import trace_service
from app.services.rag.ask_service import ask_service
from app.services.repository_service import repository_service

router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a local repository",
    description="Validates local repository path and registers it in the system.",
)
def register_repository(
    repo_in: RepositoryCreate,
    db: Annotated[Session, Depends(get_db)],
) -> RepositoryResponse:
    repo = repository_service.create_repository(db, repo_in)
    return repo


@router.get(
    "",
    response_model=list[RepositoryResponse],
    summary="List all repositories",
    description="Retrieve all registered repositories.",
)
def list_repositories(
    db: Annotated[Session, Depends(get_db)],
) -> list[RepositoryResponse]:
    return repository_service.list_repositories(db)


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get repository details",
    description="Retrieve repository record and metadata by ID.",
)
def get_repository(
    repository_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> RepositoryResponse:
    return repository_service.get_repository(db, repository_id)


@router.get(
    "/{repository_id}/files",
    response_model=RepositoryFilesResponse,
    summary="Discover repository files",
    description="Recursively discovers supported source files excluding ignored and oversized files.",
)
def get_repository_files(
    repository_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> RepositoryFilesResponse:
    repo = repository_service.get_repository(db, repository_id)
    files = repository_service.discover_files(Path(repo.path))
    return RepositoryFilesResponse(
        repository_id=repository_id,
        total_files=len(files),
        files=files,
    )


@router.post(
    "/{repository_id}/analyze",
    response_model=RepositoryAnalysisSummary,
    summary="Analyze repository code",
    description="Discovers supported source files, performs AST analysis, and persists code symbols & graph relationships.",
)
def analyze_repository(
    repository_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> RepositoryAnalysisSummary:
    return repository_service.analyze_repository(db, repository_id)


@router.get(
    "/{repository_id}/symbols",
    response_model=list[CodeSymbolResponse],
    summary="List code symbols",
    description="Retrieve code symbols in the repository with optional filtering by symbol_type and name/qualified_name search.",
)
def list_repository_symbols(
    repository_id: int,
    db: Annotated[Session, Depends(get_db)],
    symbol_type: Annotated[str | None, Query(description="Filter by symbol type (module, class, function, method)")] = None,
    search: Annotated[str | None, Query(description="Search substring in symbol name or qualified name")] = None,
) -> list[CodeSymbolResponse]:
    return repository_service.list_symbols(
        db=db,
        repository_id=repository_id,
        symbol_type=symbol_type,
        search=search,
    )


@router.get(
    "/{repository_id}/symbols/{symbol_id}",
    response_model=CodeSymbolDetailResponse,
    summary="Get symbol details",
    description="Retrieve detailed metadata and incoming/outgoing relationships for a specific code symbol.",
)
def get_symbol_detail(
    repository_id: int,
    symbol_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> CodeSymbolDetailResponse:
    return repository_service.get_symbol(
        db=db,
        repository_id=repository_id,
        symbol_id=symbol_id,
    )


@router.get(
    "/{repository_id}/relationships",
    response_model=list[CodeRelationshipResponse],
    summary="List code relationships",
    description="Retrieve all code relationship edges (contains, inherits, imports) for the repository.",
)
def list_repository_relationships(
    repository_id: int,
    db: Annotated[Session, Depends(get_db)],
    relationship_type: Annotated[str | None, Query(description="Filter by relationship type (contains, inherits, imports)")] = None,
) -> list[CodeRelationshipResponse]:
    return repository_service.list_relationships(
        db=db,
        repository_id=repository_id,
        relationship_type=relationship_type,
    )


@router.post(
    "/{repository_id}/search",
    response_model=SemanticSearchResponse,
    summary="Semantic code similarity search",
    description="Performs semantic vector search across code chunks using cosine similarity.",
)
def search_repository(
    repository_id: int,
    search_req: SemanticSearchRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SemanticSearchResponse:
    return repository_service.semantic_search(
        db=db,
        repository_id=repository_id,
        query=search_req.query,
        limit=search_req.limit,
    )


@router.post(
    "/{repository_id}/ask",
    response_model=AskResponse,
    summary="Evidence-grounded codebase question answering",
    description="Answers developer questions grounded strictly in retrieved source-code evidence and call-graph context.",
)
def ask_repository(
    repository_id: int,
    request: QuestionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AskResponse:
    return ask_service.ask(
        db=db,
        repository_id=repository_id,
        request=request,
    )


@router.post(
    "/{repository_id}/architecture/trace",
    response_model=ArchitectureTraceResponse,
    summary="Deterministic architecture execution trace",
    description="Reconstructs call flows using only the PostgreSQL code knowledge graph (CALLS relationships).",
)
def trace_repository_architecture(
    repository_id: int,
    request: ArchitectureTraceRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ArchitectureTraceResponse:
    return trace_service.trace_architecture(
        db=db,
        repository_id=repository_id,
        request=request,
    )


@router.post(
    "/{repository_id}/architecture/explain",
    response_model=ArchitectureExplainResponse,
    summary="Architecture-aware grounded RAG explanation",
    description="Explains a statically reconstructed architecture flow grounded in source evidence and call graph relationships.",
)
def explain_repository_architecture(
    repository_id: int,
    request: ArchitectureExplainRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ArchitectureExplainResponse:
    return architecture_explain_service.explain(
        db=db,
        repository_id=repository_id,
        request=request,
    )

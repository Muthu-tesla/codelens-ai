from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from app.evaluation.architecture_metrics import ArchitectureTestCase
from app.evaluation.run_real_repo_evaluation import (
    DEFAULT_REAL_REPO_PATH,
    ensure_real_repository_available,
    format_real_repo_report,
    load_real_repo_dataset,
    run_real_repo_evaluation,
)
from app.models.code_chunk import CodeChunk
from app.models.code_graph import CodeFile, CodeRelationship, CodeSymbol
from app.models.repository import Repository
from app.schemas.architecture import ArchitectureTraceRequest
from app.schemas.repository import RepositoryCreate
from app.services.architecture.symbol_resolver import start_symbol_resolver
from app.services.architecture.trace_service import trace_service
from app.services.repository_service import repository_service


def test_real_repo_dataset_loads_correctly() -> None:
    """1. Verify that real repository evaluation dataset loads and validates."""
    dataset = load_real_repo_dataset()
    assert len(dataset) >= 10
    assert all(isinstance(c, ArchitectureTestCase) for c in dataset)
    assert all(c.repository_id == "tinydb" for c in dataset)

    positive = [c for c in dataset if not c.is_negative]
    negative = [c for c in dataset if c.is_negative]
    assert len(positive) >= 8
    assert len(negative) >= 3


def test_real_repo_ingestion_and_graph_persistence(db_session: Session) -> None:
    """2. Verify ingestion, AST extraction, and call graph persistence on real repository."""
    repo_path = ensure_real_repository_available(DEFAULT_REAL_REPO_PATH)
    assert repo_path.exists()

    repo = repository_service.create_repository(
        db_session,
        RepositoryCreate(name="test_tinydb_ingest", path=str(repo_path.resolve())),
    )
    summary = repository_service.analyze_repository(db_session, repo.id)

    assert summary.errors == []
    assert summary.files_analyzed >= 15
    assert summary.classes >= 10
    assert summary.functions >= 100
    assert summary.call_relationships >= 100
    assert summary.chunks_created >= 100


def test_real_repo_idempotency_on_repeated_analysis(db_session: Session) -> None:
    """3. Verify that repeated analysis of real repository does not duplicate entities."""
    repo_path = ensure_real_repository_available(DEFAULT_REAL_REPO_PATH)
    repo = repository_service.create_repository(
        db_session,
        RepositoryCreate(name="test_tinydb_idemp", path=str(repo_path.resolve())),
    )
    s1 = repository_service.analyze_repository(db_session, repo.id)
    s2 = repository_service.analyze_repository(db_session, repo.id)

    syms_count = (
        db_session.query(CodeSymbol)
        .join(CodeFile)
        .filter(CodeFile.repository_id == repo.id)
        .count()
    )
    chunks_count = (
        db_session.query(CodeChunk)
        .filter(CodeChunk.repository_id == repo.id)
        .count()
    )
    rels_count = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo.id)
        .count()
    )

    assert syms_count == s1.chunks_created
    assert chunks_count == s1.chunks_created
    assert rels_count == s2.relationships


def test_real_repo_isolation_against_fixture_repo(db_session: Session) -> None:
    """4. Verify strict repository isolation between real repository and fixture repository."""
    repo_path = ensure_real_repository_available(DEFAULT_REAL_REPO_PATH)
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "rag_fixture_a"

    repo_real = repository_service.create_repository(
        db_session,
        RepositoryCreate(name="test_iso_real", path=str(repo_path.resolve())),
    )
    repo_fixture = repository_service.create_repository(
        db_session,
        RepositoryCreate(name="test_iso_fixture", path=str(fixture_path.resolve())),
    )
    repository_service.analyze_repository(db_session, repo_real.id)
    repository_service.analyze_repository(db_session, repo_fixture.id)

    # Question about TinyDB table insertion in fixture repo should refuse/not return tinydb symbols
    sym_in_fixture, _ = start_symbol_resolver.resolve_start_symbol(
        db_session,
        repo_fixture.id,
        "How does table insertion persist a new document in TinyDB?",
    )
    if sym_in_fixture:
        assert not sym_in_fixture.qualified_name.startswith("tinydb.")

    # Search in real repo should never return fixture symbols
    sym_in_real, _ = start_symbol_resolver.resolve_start_symbol(
        db_session,
        repo_real.id,
        "How does table insertion persist a new document in TinyDB?",
    )
    assert sym_in_real is not None
    assert sym_in_real.qualified_name.startswith("tinydb.")


def test_real_repo_trace_references_valid_source_ranges(db_session: Session) -> None:
    """5. Verify that trace nodes reference verifiable line numbers on disk."""
    repo_path = ensure_real_repository_available(DEFAULT_REAL_REPO_PATH)
    repo = repository_service.create_repository(
        db_session,
        RepositoryCreate(name="test_tinydb_lines", path=str(repo_path.resolve())),
    )
    repository_service.analyze_repository(db_session, repo.id)

    trace = trace_service.trace_architecture(
        db_session,
        repo.id,
        ArchitectureTraceRequest(start_symbol="tinydb.table.Table.insert"),
    )
    assert len(trace.nodes) >= 3
    assert len(trace.edges) >= 2

    for node in trace.nodes:
        file_path = repo_path / node.file
        assert file_path.exists(), f"Source file does not exist: {file_path}"
        assert node.line_start > 0
        assert node.line_end >= node.line_start


def test_real_repo_evaluation_runner_execution(db_session: Session) -> None:
    """6. Verify that real repository evaluation runs and calculates metrics."""
    from app.services.embedding_service import embedding_service

    current_mock = embedding_service._model
    embedding_service.set_model(None)
    try:
        repo_path = ensure_real_repository_available(DEFAULT_REAL_REPO_PATH)
        repo = repository_service.create_repository(
            db_session,
            RepositoryCreate(name="test_tinydb_eval_run", path=str(repo_path.resolve())),
        )
        summary_analysis = repository_service.analyze_repository(db_session, repo.id)

        dataset = load_real_repo_dataset()
        summary, latencies = run_real_repo_evaluation(db_session, repo.id, dataset)

        assert summary.total_queries == len(dataset)
        assert summary.start_symbol_accuracy == 1.0
        assert summary.edge_recall == 1.0
        assert summary.edge_precision == 1.0
        assert summary.exact_trace_match == 1.0
        assert summary.negative_query_accuracy == 1.0
        assert len(latencies) == len(dataset)

        report = format_real_repo_report(summary, latencies, summary_analysis.model_dump())
        assert "Real-Repository Validation Evaluation (TinyDB)" in report
        assert "Start Symbol Accuracy:     1.00" in report
        assert "REAL-01 PASS" in report
    finally:
        embedding_service.set_model(current_mock)

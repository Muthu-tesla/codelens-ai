"""
CLI runner for CodeLens Architecture Intelligence Evaluation (Phase 3D.1).

Tests the deterministic architecture intelligence layer:
natural language query -> start symbol discovery -> deterministic call-graph trace.

Usage:
    python -m app.evaluation.run_architecture_evaluation
"""
import json
import logging
import sys
from pathlib import Path
from typing import Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # Register all models with Base
from app.db.database import Base
from app.db.session import SessionLocal, engine, init_db
from app.evaluation.architecture_metrics import (
    ArchitectureEvaluationSummary,
    ArchitectureQueryEvaluationResult,
    ArchitectureTestCase,
    calculate_architecture_summary,
    evaluate_architecture_query,
)
from app.models.repository import Repository
from app.schemas.architecture import ArchitectureTraceRequest
from app.schemas.repository import RepositoryCreate
from app.services.architecture.symbol_resolver import start_symbol_resolver
from app.services.architecture.trace_service import trace_service
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)

DEFAULT_DATASET_PATH = Path(__file__).parent / "architecture_queries.json"
DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "rag_fixture_a"
)


def load_architecture_dataset(
    dataset_path: Path | str | None = None,
) -> list[ArchitectureTestCase]:
    """Load and validate the architecture query dataset from a JSON file."""
    path = Path(dataset_path) if dataset_path else DEFAULT_DATASET_PATH
    if not path.exists():
        raise FileNotFoundError(f"Architecture dataset file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Architecture dataset JSON root must be a list of query cases.")

    cases = [ArchitectureTestCase.model_validate(item) for item in data]
    return cases


def get_evaluation_session() -> Tuple[Session, bool]:
    """
    Acquire a database session for evaluation.
    Prefers the configured PostgreSQL database; if unavailable, falls back
    to an in-memory SQLite database so evaluation can run self-contained.
    """
    try:
        init_db()
        with engine.connect() as conn:
            pass
        return SessionLocal(), False
    except Exception:
        eval_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=eval_engine)
        EvalSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=eval_engine
        )
        return EvalSessionLocal(), True


def run_architecture_evaluation(
    db: Session,
    repository_id: int,
    dataset: list[ArchitectureTestCase],
) -> ArchitectureEvaluationSummary:
    """
    Run architecture evaluation across all queries in dataset against the specified repository.
    Strictly deterministic: uses symbol_resolver and trace_service with no LLM calls.
    """
    results: list[ArchitectureQueryEvaluationResult] = []

    for case in dataset:
        # 1. Resolve start symbol from natural-language question
        sym, _ = start_symbol_resolver.resolve_start_symbol(
            db=db,
            repository_id=repository_id,
            question=case.question,
        )
        resolved_name = sym.qualified_name if sym else None

        # 2. If a start symbol was resolved, trace call graph deterministically
        returned_edges: list[Tuple[str, str]] = []
        if resolved_name:
            try:
                trace_resp = trace_service.trace_architecture(
                    db=db,
                    repository_id=repository_id,
                    request=ArchitectureTraceRequest(start_symbol=resolved_name),
                )
                returned_edges = [
                    (edge.from_symbol, edge.to_symbol)
                    for edge in trace_resp.edges
                ]
            except Exception as e:
                logger.warning(
                    "Trace failed for resolved symbol %s: %s", resolved_name, e
                )

        # 3. Evaluate query against expected start symbols and edges
        res = evaluate_architecture_query(
            case=case,
            resolved_start_symbol=resolved_name,
            returned_edges=returned_edges,
        )
        results.append(res)

    return calculate_architecture_summary(results)


def format_architecture_report(summary: ArchitectureEvaluationSummary) -> str:
    """Format evaluation summary into the required human-readable report."""
    lines = [
        "Architecture Intelligence Evaluation",
        "-------------------------------------",
        "",
        f"Queries: {summary.total_queries}",
        "",
        f"Start Symbol Accuracy: {summary.start_symbol_accuracy:.2f}",
        f"Edge Precision: {summary.edge_precision:.2f}",
        f"Edge Recall: {summary.edge_recall:.2f}",
        f"Edge F1: {summary.edge_f1:.2f}",
        f"Exact Trace Match: {summary.exact_trace_match:.2f}",
        f"Negative Query Accuracy: {summary.negative_query_accuracy:.2f}",
        "",
        "Per-query results:",
        "",
    ]

    for res in summary.query_results:
        status_str = "PASS" if res.is_pass else "FAIL"
        lines.append(f"{res.case_id} {status_str}")

    return "\n".join(lines)


def main() -> int:
    """Main execution workflow for Architecture Intelligence Evaluation."""
    fixture_path = DEFAULT_FIXTURE_PATH.resolve()
    if not fixture_path.exists():
        print(
            f"Error: Fixture repository not found at {fixture_path}",
            file=sys.stderr,
        )
        return 1

    db, is_fallback = get_evaluation_session()
    try:
        # 1. Register fixture repository in database
        repo_name = "eval_arch_fixture_repo"
        repo = db.query(Repository).filter(Repository.name == repo_name).first()
        if not repo:
            repo = repository_service.create_repository(
                db,
                RepositoryCreate(name=repo_name, path=str(fixture_path)),
            )

        # 2. Analyze fixture repository
        analysis_summary = repository_service.analyze_repository(db, repo.id)
        if analysis_summary.errors:
            print(
                f"Warning: Analysis generated errors: {analysis_summary.errors}",
                file=sys.stderr,
            )

        # 3. Load evaluation queries dataset
        dataset = load_architecture_dataset()

        # 4. Execute evaluation runner
        summary = run_architecture_evaluation(
            db=db,
            repository_id=repo.id,
            dataset=dataset,
        )

        # 5. Print report
        report = format_architecture_report(summary)
        print(report)

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

"""
CLI runner for Real-Repository Architecture Intelligence Validation (Phase 3E).

Validates CodeLens AI against an unfamiliar, real open-source Python repository
(TinyDB - https://github.com/msiemens/tinydb, MIT License).

Tests:
1. Repository registration, source discovery, and AST extraction.
2. Code knowledge-graph and call-graph relationship persistence.
3. Semantic code chunking & vector embedding generation.
4. Natural language query -> start symbol resolution.
5. Deterministic call-graph execution trace reconstruction.
6. Negative / unsupported query graceful refusal without hallucination.
7. Retrieval and tracing latency metrics.

Usage:
    python -m app.evaluation.run_real_repo_evaluation
"""
import json
import logging
import os
import subprocess
import sys
import time
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
from app.models.code_graph import CodeFile, CodeRelationship, CodeSymbol
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.schemas.architecture import ArchitectureTraceRequest
from app.schemas.repository import RepositoryCreate
from app.services.architecture.symbol_resolver import start_symbol_resolver
from app.services.architecture.trace_service import trace_service
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/msiemens/tinydb.git"
REPO_VERSION = "v4.8.2 (commit 6d7c4fc3e04d398b1282876514660a33a7897b41)"
REPO_LICENSE = "MIT License"

DEFAULT_DATASET_PATH = Path(__file__).parent / "real_repo_queries.json"
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_REAL_REPO_PATH = WORKSPACE_ROOT / "evaluation_repos" / "tinydb"


def ensure_real_repository_available(target_path: Path | None = None) -> Path:
    """Ensure the real-world evaluation repository exists locally; clone if absent."""
    path = target_path or DEFAULT_REAL_REPO_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Cloning real repository %s into %s...", REPO_URL, path)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", REPO_URL, str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to clone real repository from {REPO_URL}: {exc}"
            )
    return path


def load_real_repo_dataset(
    dataset_path: Path | str | None = None,
) -> list[ArchitectureTestCase]:
    """Load and validate the real-repo evaluation query dataset."""
    path = Path(dataset_path) if dataset_path else DEFAULT_DATASET_PATH
    if not path.exists():
        raise FileNotFoundError(f"Real repository dataset not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Dataset JSON root must be a list of query test cases.")

    return [ArchitectureTestCase.model_validate(item) for item in data]


def get_evaluation_session() -> Tuple[Session, bool]:
    """
    Acquire a database session for evaluation.
    Prefers PostgreSQL; falls back to an in-memory SQLite database if PostgreSQL
    is unreachable.
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


def run_real_repo_evaluation(
    db: Session,
    repository_id: int,
    dataset: list[ArchitectureTestCase],
) -> Tuple[ArchitectureEvaluationSummary, list[dict]]:
    """
    Execute real-repo validation queries against the ingested repository.
    Measures accuracy, precision, recall, and per-query latency.
    """
    results: list[ArchitectureQueryEvaluationResult] = []
    latencies: list[dict] = []

    for case in dataset:
        # Measure retrieval & start symbol resolution latency
        t_ret_start = time.perf_counter()
        sym, _ = start_symbol_resolver.resolve_start_symbol(
            db=db,
            repository_id=repository_id,
            question=case.question,
        )
        t_ret_end = time.perf_counter()
        retrieval_ms = (t_ret_end - t_ret_start) * 1000

        resolved_name = sym.qualified_name if sym else None

        # Measure deterministic call graph tracing latency
        returned_edges: list[Tuple[str, str]] = []
        tracing_ms = 0.0
        if resolved_name:
            t_trace_start = time.perf_counter()
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
                logger.warning("Trace failed for symbol %s: %s", resolved_name, e)
            t_trace_end = time.perf_counter()
            tracing_ms = (t_trace_end - t_trace_start) * 1000

        # Evaluate against ground truth
        res = evaluate_architecture_query(
            case=case,
            resolved_start_symbol=resolved_name,
            returned_edges=returned_edges,
        )
        results.append(res)
        latencies.append({
            "case_id": case.id,
            "retrieval_ms": retrieval_ms,
            "tracing_ms": tracing_ms,
        })

    summary = calculate_architecture_summary(results)
    return summary, latencies


def format_real_repo_report(
    summary: ArchitectureEvaluationSummary,
    latencies: list[dict],
    repo_stats: dict,
) -> str:
    """Format evaluation summary, metrics, and latency measurements into a report."""
    avg_retrieval_ms = (
        sum(item["retrieval_ms"] for item in latencies) / len(latencies)
        if latencies
        else 0.0
    )
    avg_tracing_ms = (
        sum(item["tracing_ms"] for item in latencies) / len(latencies)
        if latencies
        else 0.0
    )

    lines = [
        "Real-Repository Validation Evaluation (TinyDB)",
        "===============================================",
        f"Repository: {REPO_URL}",
        f"Version:    {REPO_VERSION}",
        f"License:    {REPO_LICENSE}",
        "",
        "Ingestion Statistics:",
        f"  Files Analyzed:            {repo_stats.get('files_analyzed', 0)}",
        f"  Classes Indexed:           {repo_stats.get('classes', 0)}",
        f"  Functions & Methods:       {repo_stats.get('functions', 0)}",
        f"  CALLS Edges Discovered:    {repo_stats.get('call_relationships', 0)}",
        f"  Code Chunks Created:       {repo_stats.get('chunks_created', 0)}",
        f"  Embeddings Generated:      {repo_stats.get('embeddings_generated', 0)}",
        f"  Ingestion Errors:          {len(repo_stats.get('errors', []))}",
        "",
        f"Queries Evaluated: {summary.total_queries} ({summary.positive_queries} positive, {summary.negative_queries} negative)",
        "",
        "Evaluation Metrics:",
        f"  Start Symbol Accuracy:     {summary.start_symbol_accuracy:.2f}",
        f"  Edge Precision:            {summary.edge_precision:.2f}",
        f"  Edge Recall:               {summary.edge_recall:.2f}",
        f"  Edge F1:                   {summary.edge_f1:.2f}",
        f"  Exact Trace Match:         {summary.exact_trace_match:.2f}",
        f"  Negative Query Accuracy:   {summary.negative_query_accuracy:.2f}",
        "",
        "Latency Measurements:",
        f"  Avg Semantic Retrieval:    {avg_retrieval_ms:.1f} ms",
        f"  Avg Architecture Tracing:  {avg_tracing_ms:.1f} ms",
        "",
        "Per-query Results:",
    ]

    for res, lat in zip(summary.query_results, latencies):
        status_str = "PASS" if res.is_pass else "FAIL"
        resolved_str = res.resolved_start_symbol or "None (Refused)"
        lines.append(
            f"  {res.case_id} {status_str:4s} | "
            f"Resolved: {resolved_str:<35s} | "
            f"Ret: {lat['retrieval_ms']:5.1f}ms | Trace: {lat['tracing_ms']:4.1f}ms"
        )

    return "\n".join(lines)


def main() -> int:
    """Main workflow for Phase 3E Real-Repository Validation."""
    try:
        repo_path = ensure_real_repository_available()
    except Exception as e:
        print(f"Error: Unable to acquire real evaluation repository: {e}", file=sys.stderr)
        return 1

    db, is_fallback = get_evaluation_session()
    try:
        # 1. Register real repository
        repo_name = "real_eval_tinydb"
        repo = db.query(Repository).filter(Repository.name == repo_name).first()
        if not repo:
            repo = repository_service.create_repository(
                db,
                RepositoryCreate(name=repo_name, path=str(repo_path.resolve())),
            )

        # 2. Ingest & analyze repository
        analysis_summary = repository_service.analyze_repository(db, repo.id)
        repo_stats = analysis_summary.model_dump()

        # 3. Load real-repo evaluation queries
        dataset = load_real_repo_dataset()

        # 4. Run evaluation
        summary, latencies = run_real_repo_evaluation(
            db=db,
            repository_id=repo.id,
            dataset=dataset,
        )

        # 5. Output report
        report = format_real_repo_report(summary, latencies, repo_stats)
        print(report)

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

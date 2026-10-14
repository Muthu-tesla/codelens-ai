import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.metrics import (
    calculate_mrr,
    calculate_recall_at_k,
    evaluate_query,
)
from app.evaluation.schemas import (
    EvaluationCase,
    EvaluationSummary,
    QueryEvaluationResult,
)
from app.services.repository_service import repository_service

logger = logging.getLogger(__name__)

DEFAULT_DATASET_PATH = Path(__file__).parent / "datasets" / "evaluation_queries.json"
DEFAULT_FIXTURE_PATH = Path(__file__).parent / "fixture_repo"


def load_dataset(dataset_path: Path | str | None = None) -> list[EvaluationCase]:
    """Load and validate the evaluation query dataset from a JSON file."""
    path = Path(dataset_path) if dataset_path else DEFAULT_DATASET_PATH
    if not path.exists():
        raise FileNotFoundError(f"Evaluation dataset file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Evaluation dataset JSON root must be a list of query cases.")

    cases = [EvaluationCase.model_validate(item) for item in data]
    return cases


def format_evaluation_report(summary: EvaluationSummary) -> str:
    """Format evaluation summary into a clean, human-readable terminal report."""
    lines: list[str] = [
        "CodeLens Retrieval Evaluation",
        "==============================",
        "",
        f"Queries: {summary.total_queries}",
        "",
    ]

    for k in sorted(summary.recall_at_k.keys()):
        lines.append(f"Recall@{k}: {summary.recall_at_k[k]:.2f}")

    lines.append("")
    lines.append(f"MRR: {summary.mrr:.2f}")
    lines.append("")
    lines.append("Per-query results")
    lines.append("-----------------")

    for res in summary.query_results:
        status_icon = "[HIT]" if res.first_relevant_rank is not None else "[MISS]"
        lines.append("")
        lines.append(f"{res.case_id} {status_icon}")
        lines.append(f"Query: {res.query}")
        lines.append("Expected:")
        for exp in res.expected_symbols:
            lines.append(f"  {exp}")

        if res.first_relevant_rank is not None:
            hit_symbol = res.retrieved_symbols[res.first_relevant_rank - 1]
            score_str = ""
            if len(res.retrieved_scores) >= res.first_relevant_rank:
                score_str = f"  similarity={res.retrieved_scores[res.first_relevant_rank - 1]:.2f}"
            lines.append(f"Rank {res.first_relevant_rank}:")
            lines.append(f"  {hit_symbol}")
            if score_str:
                lines.append(score_str)
        else:
            lines.append("Expected symbols not retrieved")
            if res.retrieved_symbols:
                top_sym = res.retrieved_symbols[0]
                lines.append("Top result:")
                lines.append(f"  {top_sym}")
                if res.retrieved_scores:
                    lines.append(f"  similarity={res.retrieved_scores[0]:.2f}")
            else:
                lines.append("Top result: (no chunks retrieved)")

    lines.append("")
    return "\n".join(lines)


class EvaluationRunner:
    """
    Executes retrieval evaluation by running dataset queries against
    semantic code search and computing standardized retrieval metrics.
    """

    def __init__(self, k_values: list[int] | None = None) -> None:
        self.k_values = k_values or [1, 3, 5]

    def evaluate_queries(
        self,
        db: Session,
        repository_id: int,
        dataset: list[EvaluationCase],
    ) -> EvaluationSummary:
        """
        Execute semantic search for all evaluation cases and calculate metrics.
        Does not duplicate search logic; delegates directly to repository_service.
        """
        if not dataset:
            return EvaluationSummary(
                total_queries=0,
                recall_at_k={k: 0.0 for k in self.k_values},
                mrr=0.0,
                query_results=[],
            )

        max_k = max(self.k_values)
        results: list[QueryEvaluationResult] = []

        for case in dataset:
            search_resp = repository_service.semantic_search(
                db=db,
                repository_id=repository_id,
                query=case.query,
                limit=max_k,
            )

            retrieved_symbols = [
                item.qualified_name for item in search_resp.results
                if item.qualified_name is not None
            ]
            retrieved_scores = [item.similarity for item in search_resp.results]

            res = evaluate_query(
                case=case,
                retrieved_symbols=retrieved_symbols,
                retrieved_scores=retrieved_scores,
                k_values=self.k_values,
            )
            results.append(res)

        recall_map = {k: calculate_recall_at_k(results, k) for k in self.k_values}
        mrr_val = calculate_mrr(results)

        return EvaluationSummary(
            total_queries=len(dataset),
            recall_at_k=recall_map,
            mrr=mrr_val,
            query_results=results,
        )

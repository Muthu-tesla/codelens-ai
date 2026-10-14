"""Evaluation package for CodeLens retrieval benchmarking."""
from app.evaluation.metrics import (
    calculate_mrr,
    calculate_recall_at_k,
    evaluate_query,
)
from app.evaluation.runner import (
    DEFAULT_DATASET_PATH,
    DEFAULT_FIXTURE_PATH,
    EvaluationRunner,
    format_evaluation_report,
    load_dataset,
)
from app.evaluation.schemas import (
    EvaluationCase,
    EvaluationSummary,
    QueryEvaluationResult,
)

__all__ = [
    "DEFAULT_DATASET_PATH",
    "DEFAULT_FIXTURE_PATH",
    "EvaluationCase",
    "EvaluationRunner",
    "EvaluationSummary",
    "QueryEvaluationResult",
    "calculate_mrr",
    "calculate_recall_at_k",
    "evaluate_query",
    "format_evaluation_report",
    "load_dataset",
]

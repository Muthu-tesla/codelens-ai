from typing import Tuple
from pydantic import BaseModel, Field


class ArchitectureTestCase(BaseModel):
    """Schema for an individual architecture evaluation test case."""

    id: str = Field(..., description="Unique test case identifier (e.g. ARCH-01)")
    question: str = Field(..., min_length=1, description="Natural-language developer query")
    repository_id: str = Field(
        default="rag_fixture_a",
        description="Target fixture repository identifier",
    )
    category: str | None = Field(default=None, description="Domain category (e.g. order_flow, payment_flow)")
    expected_start_symbols: list[str] = Field(
        default_factory=list,
        description="List of valid start symbol qualified names",
    )
    expected_edges: list[Tuple[str, str]] = Field(
        default_factory=list,
        description="Expected call relationships as (from_symbol, to_symbol) tuples",
    )
    is_negative: bool = Field(
        default=False,
        description="True if query is unsupported and must NOT produce an architecture trace",
    )


class ArchitectureQueryEvaluationResult(BaseModel):
    """Evaluation output for a single architecture query."""

    case_id: str
    question: str
    repository_id: str = "rag_fixture_a"
    category: str | None = None
    is_negative: bool = False
    expected_start_symbols: list[str] = Field(default_factory=list)
    resolved_start_symbol: str | None = None
    expected_edges: list[Tuple[str, str]] = Field(default_factory=list)
    returned_edges: list[Tuple[str, str]] = Field(default_factory=list)
    start_symbol_match: bool = False
    edge_precision: float = 0.0
    edge_recall: float = 0.0
    edge_f1: float = 0.0
    exact_trace_match: bool = False
    negative_query_success: bool = True
    is_pass: bool = False


class ArchitectureEvaluationSummary(BaseModel):
    """Aggregated evaluation metrics across all architecture dataset queries."""

    total_queries: int
    positive_queries: int
    negative_queries: int
    start_symbol_accuracy: float = 0.0
    edge_precision: float = 0.0
    edge_recall: float = 0.0
    edge_f1: float = 0.0
    exact_trace_match: float = 0.0
    negative_query_accuracy: float = 0.0
    query_results: list[ArchitectureQueryEvaluationResult] = Field(default_factory=list)


def calculate_edge_precision(
    expected_edges: set[Tuple[str, str]],
    returned_edges: set[Tuple[str, str]],
) -> float:
    """Calculate precision of returned edges against expected edges."""
    if not expected_edges:
        return 1.0 if not returned_edges else 0.0
    if not returned_edges:
        return 0.0
    intersection = expected_edges.intersection(returned_edges)
    return len(intersection) / len(returned_edges)


def calculate_edge_recall(
    expected_edges: set[Tuple[str, str]],
    returned_edges: set[Tuple[str, str]],
) -> float:
    """Calculate recall of expected edges found in returned edges."""
    if not expected_edges:
        return 1.0
    intersection = expected_edges.intersection(returned_edges)
    return len(intersection) / len(expected_edges)


def calculate_edge_f1(precision: float, recall: float) -> float:
    """Calculate harmonic mean F1 from precision and recall."""
    if (precision + recall) == 0.0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)


def evaluate_architecture_query(
    case: ArchitectureTestCase,
    resolved_start_symbol: str | None,
    returned_edges: list[Tuple[str, str]],
) -> ArchitectureQueryEvaluationResult:
    """
    Evaluate a single architecture query against ground-truth expectations.
    Handles start symbol matching, graph edge precision/recall/F1,
    exact trace match, and negative query refusal verification.
    """
    expected_edge_set: set[Tuple[str, str]] = {
        (e[0], e[1]) for e in case.expected_edges
    }
    returned_edge_set: set[Tuple[str, str]] = {
        (e[0], e[1]) for e in returned_edges
    }

    if case.is_negative:
        # Negative query: system must refuse to produce an arbitrary trace
        refused = resolved_start_symbol is None
        no_edges = len(returned_edges) == 0
        success = refused and no_edges
        return ArchitectureQueryEvaluationResult(
            case_id=case.id,
            question=case.question,
            repository_id=case.repository_id,
            category=case.category,
            is_negative=True,
            expected_start_symbols=[],
            resolved_start_symbol=resolved_start_symbol,
            expected_edges=[],
            returned_edges=returned_edges,
            start_symbol_match=refused,
            edge_precision=1.0 if no_edges else 0.0,
            edge_recall=1.0,
            edge_f1=1.0 if no_edges else 0.0,
            exact_trace_match=no_edges,
            negative_query_success=refused,
            is_pass=success,
        )

    # Positive query: system must discover a valid start symbol and trace
    start_match = (
        resolved_start_symbol in case.expected_start_symbols
        if resolved_start_symbol is not None
        else False
    )
    precision = calculate_edge_precision(expected_edge_set, returned_edge_set)
    recall = calculate_edge_recall(expected_edge_set, returned_edge_set)
    f1 = calculate_edge_f1(precision, recall)
    exact_match = (expected_edge_set == returned_edge_set)

    is_pass = start_match and exact_match

    return ArchitectureQueryEvaluationResult(
        case_id=case.id,
        question=case.question,
        repository_id=case.repository_id,
        category=case.category,
        is_negative=False,
        expected_start_symbols=case.expected_start_symbols,
        resolved_start_symbol=resolved_start_symbol,
        expected_edges=[(e[0], e[1]) for e in case.expected_edges],
        returned_edges=returned_edges,
        start_symbol_match=start_match,
        edge_precision=precision,
        edge_recall=recall,
        edge_f1=f1,
        exact_trace_match=exact_match,
        negative_query_success=True,
        is_pass=is_pass,
    )


def calculate_architecture_summary(
    results: list[ArchitectureQueryEvaluationResult],
) -> ArchitectureEvaluationSummary:
    """
    Compute macro-averaged evaluation metrics across all architecture queries.
    """
    if not results:
        return ArchitectureEvaluationSummary(
            total_queries=0,
            positive_queries=0,
            negative_queries=0,
            start_symbol_accuracy=0.0,
            edge_precision=0.0,
            edge_recall=0.0,
            edge_f1=0.0,
            exact_trace_match=0.0,
            negative_query_accuracy=1.0,
            query_results=[],
        )

    positive_results = [r for r in results if not r.is_negative]
    negative_results = [r for r in results if r.is_negative]

    num_pos = len(positive_results)
    num_neg = len(negative_results)

    start_acc = (
        sum(1 for r in positive_results if r.start_symbol_match) / num_pos
        if num_pos > 0
        else 0.0
    )
    edge_prec = (
        sum(r.edge_precision for r in positive_results) / num_pos
        if num_pos > 0
        else 0.0
    )
    edge_rec = (
        sum(r.edge_recall for r in positive_results) / num_pos
        if num_pos > 0
        else 0.0
    )
    edge_f1_val = (
        sum(r.edge_f1 for r in positive_results) / num_pos
        if num_pos > 0
        else 0.0
    )
    exact_match = (
        sum(1 for r in positive_results if r.exact_trace_match) / num_pos
        if num_pos > 0
        else 0.0
    )
    neg_acc = (
        sum(1 for r in negative_results if r.negative_query_success) / num_neg
        if num_neg > 0
        else 1.0
    )

    return ArchitectureEvaluationSummary(
        total_queries=len(results),
        positive_queries=num_pos,
        negative_queries=num_neg,
        start_symbol_accuracy=start_acc,
        edge_precision=edge_prec,
        edge_recall=edge_rec,
        edge_f1=edge_f1_val,
        exact_trace_match=exact_match,
        negative_query_accuracy=neg_acc,
        query_results=results,
    )

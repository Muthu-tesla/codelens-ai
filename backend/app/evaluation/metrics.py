from app.evaluation.schemas import EvaluationCase, QueryEvaluationResult


def evaluate_query(
    case: EvaluationCase,
    retrieved_symbols: list[str],
    retrieved_scores: list[float] | None = None,
    k_values: list[int] | None = None,
) -> QueryEvaluationResult:
    """
    Evaluate retrieval results for an individual evaluation case.
    Matches retrieved symbol qualified names against expected symbols.
    """
    if k_values is None:
        k_values = [1, 3, 5]

    scores = retrieved_scores or []
    expected_set = set(case.expected_symbols)

    first_rank: int | None = None
    for idx, sym in enumerate(retrieved_symbols, start=1):
        if sym in expected_set:
            first_rank = idx
            break

    hits_at_k: dict[int, bool] = {}
    for k in k_values:
        hits_at_k[k] = (first_rank is not None and first_rank <= k)

    reciprocal_rank = (1.0 / first_rank) if first_rank is not None else 0.0

    return QueryEvaluationResult(
        case_id=case.id,
        query=case.query,
        expected_symbols=case.expected_symbols,
        retrieved_symbols=retrieved_symbols,
        retrieved_scores=scores,
        first_relevant_rank=first_rank,
        hits_at_k=hits_at_k,
        reciprocal_rank=round(reciprocal_rank, 4),
    )


def calculate_recall_at_k(query_results: list[QueryEvaluationResult], k: int) -> float:
    """
    Calculate Recall@K across all query evaluation results.
    A query is successful if at least one expected symbol appears within top K results.
    """
    if not query_results:
        return 0.0

    successful_queries = sum(
        1 for r in query_results
        if r.first_relevant_rank is not None and r.first_relevant_rank <= k
    )
    return round(successful_queries / len(query_results), 4)


def calculate_mrr(query_results: list[QueryEvaluationResult]) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR) across all query evaluation results.
    MRR = (1 / |Q|) * sum(1 / rank_of_first_relevant_result)
    Queries with no relevant retrieved symbols contribute 0.
    """
    if not query_results:
        return 0.0

    total_rr = sum(r.reciprocal_rank for r in query_results)
    return round(total_rr / len(query_results), 4)

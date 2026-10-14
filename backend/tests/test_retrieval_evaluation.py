from pathlib import Path
import pytest
from pydantic import ValidationError

from app.evaluation.metrics import (
    calculate_mrr,
    calculate_recall_at_k,
    evaluate_query,
)
from app.evaluation.runner import (
    DEFAULT_DATASET_PATH,
    EvaluationRunner,
    format_evaluation_report,
    load_dataset,
)
from app.evaluation.schemas import (
    EvaluationCase,
    EvaluationSummary,
    QueryEvaluationResult,
)


def test_dataset_loading():
    """Test 1: Dataset loading successfully reads the JSON file."""
    cases = load_dataset(DEFAULT_DATASET_PATH)
    assert isinstance(cases, list)
    assert len(cases) >= 15
    assert all(isinstance(c, EvaluationCase) for c in cases)


def test_dataset_schema_validation():
    """Test 2: Dataset schema validation requires query and non-empty expected symbols."""
    # Valid case
    case = EvaluationCase(
        id="T01",
        query="Where is payment handled?",
        expected_symbols=["app.services.pay.process"],
        category="payments",
    )
    assert case.id == "T01"

    # Missing query raises error
    with pytest.raises(ValidationError):
        EvaluationCase(id="T02", query="", expected_symbols=["app.sym"])

    # Empty expected symbols raises error
    with pytest.raises(ValidationError):
        EvaluationCase(id="T03", query="Some query", expected_symbols=[])


def test_evaluation_query_execution():
    """Test 3: Query evaluation maps retrieved symbols to expected targets."""
    case = EvaluationCase(
        id="Q01",
        query="Where are orders created?",
        expected_symbols=["orders.service.OrderService.create_order"],
    )
    retrieved = [
        "orders.repository.OrderRepository.save",
        "orders.service.OrderService.create_order",
        "orders.service.OrderService.cancel_order",
    ]
    scores = [0.85, 0.82, 0.70]

    res = evaluate_query(case, retrieved, scores, k_values=[1, 3, 5])
    assert res.case_id == "Q01"
    assert res.first_relevant_rank == 2
    assert res.reciprocal_rank == 0.5
    assert res.hits_at_k[1] is False
    assert res.hits_at_k[3] is True
    assert res.hits_at_k[5] is True


def test_recall_at_1_calculation():
    """Test 4: Recall@1 calculates fraction of queries with hit at rank 1."""
    results = [
        QueryEvaluationResult(
            case_id="Q1", query="q1", expected_symbols=["s1"], first_relevant_rank=1, reciprocal_rank=1.0
        ),
        QueryEvaluationResult(
            case_id="Q2", query="q2", expected_symbols=["s2"], first_relevant_rank=2, reciprocal_rank=0.5
        ),
        QueryEvaluationResult(
            case_id="Q3", query="q3", expected_symbols=["s3"], first_relevant_rank=None, reciprocal_rank=0.0
        ),
        QueryEvaluationResult(
            case_id="Q4", query="q4", expected_symbols=["s4"], first_relevant_rank=1, reciprocal_rank=1.0
        ),
    ]
    # 2 hits at rank 1 out of 4 queries = 0.50
    recall1 = calculate_recall_at_k(results, 1)
    assert recall1 == 0.50


def test_recall_at_3_calculation():
    """Test 5: Recall@3 calculates fraction of queries with hit in top 3."""
    results = [
        QueryEvaluationResult(
            case_id="Q1", query="q1", expected_symbols=["s1"], first_relevant_rank=1, reciprocal_rank=1.0
        ),
        QueryEvaluationResult(
            case_id="Q2", query="q2", expected_symbols=["s2"], first_relevant_rank=2, reciprocal_rank=0.5
        ),
        QueryEvaluationResult(
            case_id="Q3", query="q3", expected_symbols=["s3"], first_relevant_rank=3, reciprocal_rank=0.3333
        ),
        QueryEvaluationResult(
            case_id="Q4", query="q4", expected_symbols=["s4"], first_relevant_rank=4, reciprocal_rank=0.25
        ),
    ]
    # 3 hits in top 3 out of 4 queries = 0.75
    recall3 = calculate_recall_at_k(results, 3)
    assert recall3 == 0.75


def test_recall_at_5_calculation():
    """Test 6: Recall@5 calculates fraction of queries with hit in top 5."""
    results = [
        QueryEvaluationResult(
            case_id="Q1", query="q1", expected_symbols=["s1"], first_relevant_rank=5, reciprocal_rank=0.2
        ),
        QueryEvaluationResult(
            case_id="Q2", query="q2", expected_symbols=["s2"], first_relevant_rank=6, reciprocal_rank=0.1667
        ),
    ]
    # 1 hit in top 5 out of 2 queries = 0.50
    recall5 = calculate_recall_at_k(results, 5)
    assert recall5 == 0.50


def test_mrr_calculation():
    """Test 7: MRR computes average reciprocal rank across all queries."""
    results = [
        QueryEvaluationResult(
            case_id="Q1", query="q1", expected_symbols=["s1"], first_relevant_rank=1, reciprocal_rank=1.0
        ),
        QueryEvaluationResult(
            case_id="Q2", query="q2", expected_symbols=["s2"], first_relevant_rank=2, reciprocal_rank=0.5
        ),
        QueryEvaluationResult(
            case_id="Q3", query="q3", expected_symbols=["s3"], first_relevant_rank=None, reciprocal_rank=0.0
        ),
        QueryEvaluationResult(
            case_id="Q4", query="q4", expected_symbols=["s4"], first_relevant_rank=4, reciprocal_rank=0.25
        ),
    ]
    # Total RR = 1.0 + 0.5 + 0.0 + 0.25 = 1.75 / 4 = 0.4375
    mrr = calculate_mrr(results)
    assert mrr == 0.4375


def test_relevant_result_detection():
    """Test 8: First occurrence of an expected symbol determines relevant rank."""
    case = EvaluationCase(
        id="Q08",
        query="find user",
        expected_symbols=["users.service.UserService.get_user_by_email"],
    )
    retrieved = [
        "users.service.UserService.register_user",
        "users.service.UserService.get_user_by_email",
    ]
    res = evaluate_query(case, retrieved, [0.8, 0.75])
    assert res.first_relevant_rank == 2
    assert res.reciprocal_rank == 0.5


def test_missing_expected_symbol_handling():
    """Test 9: Queries with no expected symbols retrieved yield rank None and RR 0.0."""
    case = EvaluationCase(
        id="Q09",
        query="unknown feature",
        expected_symbols=["missing.module.Symbol"],
    )
    retrieved = ["other.symbol.A", "other.symbol.B"]
    res = evaluate_query(case, retrieved, [0.4, 0.3])
    assert res.first_relevant_rank is None
    assert res.reciprocal_rank == 0.0
    assert all(hit is False for hit in res.hits_at_k.values())


def test_multiple_expected_symbols():
    """Test 10: Multiple expected symbols match on whichever appears first."""
    case = EvaluationCase(
        id="Q10",
        query="payment card",
        expected_symbols=[
            "payments.service.PaymentService.process_payment",
            "payments.gateway.StripeGateway.charge_card",
        ],
    )
    # StripeGateway appears at rank 1
    retrieved = [
        "payments.gateway.StripeGateway.charge_card",
        "payments.service.PaymentService.process_payment",
    ]
    res = evaluate_query(case, retrieved, [0.9, 0.85])
    assert res.first_relevant_rank == 1
    assert res.reciprocal_rank == 1.0


def test_empty_evaluation_dataset_handling():
    """Test 11: Empty dataset produces zero counts and 0.0 metrics without errors."""
    runner = EvaluationRunner()
    # Call calculate functions on empty lists
    assert calculate_recall_at_k([], 1) == 0.0
    assert calculate_recall_at_k([], 3) == 0.0
    assert calculate_recall_at_k([], 5) == 0.0
    assert calculate_mrr([]) == 0.0

    # Summary formatting with empty results
    summary = EvaluationSummary(total_queries=0, recall_at_k={1: 0.0, 3: 0.0, 5: 0.0}, mrr=0.0)
    report = format_evaluation_report(summary)
    assert "Queries: 0" in report
    assert "MRR: 0.00" in report


def test_evaluation_report_generation():
    """Test 12: Report generation includes header, metrics, and per-query details."""
    query_results = [
        QueryEvaluationResult(
            case_id="Q01",
            query="Where is payment handled?",
            expected_symbols=["payments.service.PaymentService.process_payment"],
            retrieved_symbols=["payments.service.PaymentService.process_payment"],
            retrieved_scores=[0.89],
            first_relevant_rank=1,
            reciprocal_rank=1.0,
        ),
        QueryEvaluationResult(
            case_id="Q02",
            query="Where is inventory updated?",
            expected_symbols=["inventory.service.update"],
            retrieved_symbols=["wrong.symbol"],
            retrieved_scores=[0.35],
            first_relevant_rank=None,
            reciprocal_rank=0.0,
        ),
    ]
    summary = EvaluationSummary(
        total_queries=2,
        recall_at_k={1: 0.50, 3: 0.50, 5: 0.50},
        mrr=0.50,
        query_results=query_results,
    )

    report = format_evaluation_report(summary)
    assert "CodeLens Retrieval Evaluation" in report
    assert "Queries: 2" in report
    assert "Recall@1: 0.50" in report
    assert "MRR: 0.50" in report
    assert "Q01 [HIT]" in report
    assert "Rank 1:" in report
    assert "Q02 [MISS]" in report
    assert "Expected symbols not retrieved" in report

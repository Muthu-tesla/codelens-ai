from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from app.evaluation.architecture_metrics import (
    ArchitectureTestCase,
    calculate_architecture_summary,
    calculate_edge_f1,
    calculate_edge_precision,
    calculate_edge_recall,
    evaluate_architecture_query,
)
from app.evaluation.run_architecture_evaluation import (
    format_architecture_report,
    load_architecture_dataset,
    run_architecture_evaluation,
)
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate
from app.services.repository_service import repository_service


def test_dataset_loads_correctly() -> None:
    """1. Verify that the architecture evaluation dataset loads and validates correctly."""
    dataset = load_architecture_dataset()
    assert len(dataset) >= 15
    assert all(isinstance(c, ArchitectureTestCase) for c in dataset)
    assert all(bool(c.repository_id) for c in dataset)
    categories = {c.category for c in dataset}
    assert {
        "order_flow",
        "payment_flow",
        "inventory",
        "authentication",
        "repository_database",
        "negative_unsupported",
    }.issubset(categories)


def test_expected_symbols_are_valid() -> None:
    """2. Verify that all expected start symbols are well-formed qualified names."""
    dataset = load_architecture_dataset()
    positive_cases = [c for c in dataset if not c.is_negative]
    assert len(positive_cases) >= 10
    for case in positive_cases:
        assert len(case.expected_start_symbols) > 0, f"Case {case.id} must define expected start symbols"
        for sym in case.expected_start_symbols:
            assert "." in sym, f"Expected qualified name with module path in {case.id}: {sym}"


def test_expected_edges_are_valid() -> None:
    """3. Verify that all expected edges are formatted as valid (from, to) pairs."""
    dataset = load_architecture_dataset()
    for case in dataset:
        for edge in case.expected_edges:
            assert len(edge) == 2, f"Edge in {case.id} must have exactly 2 elements"
            from_sym, to_sym = edge
            assert "." in from_sym, f"Edge source must be qualified in {case.id}: {from_sym}"
            assert "." in to_sym, f"Edge target must be qualified in {case.id}: {to_sym}"


def test_start_symbol_accuracy_metric() -> None:
    """4. Verify start symbol accuracy metric calculation."""
    case = ArchitectureTestCase(
        id="T01",
        question="How does order create?",
        expected_start_symbols=["orders.service.OrderService.create_order"],
    )
    res_correct = evaluate_architecture_query(case, "orders.service.OrderService.create_order", [])
    assert res_correct.start_symbol_match is True

    res_wrong = evaluate_architecture_query(case, "payments.service.PaymentService.process", [])
    assert res_wrong.start_symbol_match is False


def test_edge_precision_metric() -> None:
    """5. Verify edge precision metric calculation."""
    expected = {("A", "B"), ("B", "C")}
    returned_exact = {("A", "B"), ("B", "C")}
    assert calculate_edge_precision(expected, returned_exact) == 1.0

    returned_extra = {("A", "B"), ("B", "C"), ("C", "D")}
    assert calculate_edge_precision(expected, returned_extra) == pytest.approx(2 / 3)

    assert calculate_edge_precision(expected, set()) == 0.0
    assert calculate_edge_precision(set(), set()) == 1.0


def test_edge_recall_metric() -> None:
    """6. Verify edge recall metric calculation."""
    expected = {("A", "B"), ("B", "C")}
    returned_exact = {("A", "B"), ("B", "C")}
    assert calculate_edge_recall(expected, returned_exact) == 1.0

    returned_partial = {("A", "B")}
    assert calculate_edge_recall(expected, returned_partial) == 0.5

    assert calculate_edge_recall(expected, set()) == 0.0
    assert calculate_edge_recall(set(), set()) == 1.0


def test_edge_f1_metric() -> None:
    """7. Verify harmonic mean F1 calculation."""
    assert calculate_edge_f1(1.0, 1.0) == 1.0
    assert calculate_edge_f1(0.0, 1.0) == 0.0
    assert calculate_edge_f1(0.0, 0.0) == 0.0
    assert calculate_edge_f1(0.5, 1.0) == pytest.approx(2 / 3)


def test_exact_trace_match_metric() -> None:
    """8. Verify exact trace match evaluation."""
    case = ArchitectureTestCase(
        id="T02",
        question="How does payment work?",
        expected_start_symbols=["payments.service.PaymentService.process"],
        expected_edges=[("payments.service.PaymentService.process", "payments.gateway.StripeGateway.charge")],
    )
    res_exact = evaluate_architecture_query(
        case,
        "payments.service.PaymentService.process",
        [("payments.service.PaymentService.process", "payments.gateway.StripeGateway.charge")],
    )
    assert res_exact.exact_trace_match is True
    assert res_exact.is_pass is True

    res_mismatch = evaluate_architecture_query(
        case,
        "payments.service.PaymentService.process",
        [("payments.service.PaymentService.process", "payments.gateway.OtherGateway.charge")],
    )
    assert res_mismatch.exact_trace_match is False
    assert res_mismatch.is_pass is False


def test_negative_query_accuracy_metric() -> None:
    """9. Verify negative query accuracy metric for unsupported queries."""
    neg_case = ArchitectureTestCase(
        id="T03",
        question="How does OAuth work?",
        is_negative=True,
    )
    res_refused = evaluate_architecture_query(neg_case, None, [])
    assert res_refused.negative_query_success is True
    assert res_refused.is_pass is True

    res_hallucinated = evaluate_architecture_query(neg_case, "auth.service.AuthService.login", [])
    assert res_hallucinated.negative_query_success is False
    assert res_hallucinated.is_pass is False


def test_evaluation_runner_executes_successfully(db_session: Session) -> None:
    """10. Verify that the architecture evaluation runner runs on fixture repo and outputs summary."""
    from app.services.embedding_service import embedding_service

    current_mock = embedding_service._model
    embedding_service.set_model(None)
    try:
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "rag_fixture_a"
        repo = repository_service.create_repository(
            db_session,
            RepositoryCreate(name="test_arch_eval_repo", path=str(fixture_path)),
        )
        repository_service.analyze_repository(db_session, repo.id)

        dataset = load_architecture_dataset()
        summary = run_architecture_evaluation(db_session, repo.id, dataset)

        assert summary.total_queries == len(dataset)
        assert summary.start_symbol_accuracy == 1.0
        assert summary.negative_query_accuracy == 1.0
        assert summary.edge_recall == 1.0
        assert summary.edge_precision == 1.0
        assert summary.exact_trace_match == 1.0

        report = format_architecture_report(summary)
        assert "Architecture Intelligence Evaluation" in report
        assert "Start Symbol Accuracy: 1.00" in report
        assert "ARCH-01 PASS" in report
    finally:
        embedding_service.set_model(current_mock)

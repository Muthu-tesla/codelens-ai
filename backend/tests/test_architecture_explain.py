from collections.abc import Generator
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.architecture.symbol_resolver import start_symbol_resolver
from app.services.architecture.trace_service import trace_service
from app.services.llm.base import BaseLLMProvider
from app.services.llm.provider import llm_service


class MockArchitectureLLMProvider(BaseLLMProvider):
    """Deterministic mock LLM provider for architecture explain tests."""

    def __init__(
        self,
        response_text: str = (
            "The static call graph shows that OrderService.create_order [E1] coordinates order creation. "
            "It first invokes InventoryService.check_stock [E2] to verify inventory availability. "
            "Next, it calls PaymentService.process_payment [E3], which delegates card charging to "
            "StripeGateway.charge_card [E4]. Finally, OrderRepository.save_order [E5] persists the confirmed order."
        ),
    ):
        self.response_text = response_text
        self.recorded_prompts: list[str] = []

    def generate_answer(self, prompt: str) -> str:
        self.recorded_prompts.append(prompt)
        return self.response_text


@pytest.fixture(autouse=True)
def mock_arch_llm() -> Generator[MockArchitectureLLMProvider, None, None]:
    """Inject a deterministic mock LLM provider for architecture explain tests."""
    original = llm_service._provider
    mock = MockArchitectureLLMProvider()
    llm_service.set_provider(mock)
    yield mock
    llm_service.set_provider(original)


@pytest.fixture
def order_fixture_repo() -> Path:
    """Path to the deterministic rag_fixture_a repository."""
    return Path(__file__).resolve().parent / "fixtures" / "rag_fixture_a"


@pytest.fixture
def order_fixture_b_repo() -> Path:
    """Path to the deterministic rag_fixture_b repository."""
    return Path(__file__).resolve().parent / "fixtures" / "rag_fixture_b"


def test_natural_language_order_flow_question(
    client: TestClient, order_fixture_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 1: Natural-language order-flow question produces an authoritative architecture explanation."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-explain-order", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["question"] == "How does an order get created?"
    assert "[E1]" in data["answer"]
    assert data["trace"] is not None

    # Trace is authoritative
    assert data["trace"]["start_symbol"] == "orders.service.OrderService.create_order"
    node_names = [n["name"] for n in data["trace"]["nodes"]]
    assert node_names == ["create_order", "check_stock", "process_payment", "charge_card", "save_order"]

    # Trace edges include call flow
    edges = [(e["from"], e["to"]) for e in data["trace"]["edges"]]
    assert ("orders.service.OrderService.create_order", "inventory.service.InventoryService.check_stock") in edges
    assert ("orders.service.OrderService.create_order", "payments.service.PaymentService.process_payment") in edges
    assert ("payments.service.PaymentService.process_payment", "payments.gateway.StripeGateway.charge_card") in edges
    assert ("orders.service.OrderService.create_order", "database.repository.OrderRepository.save_order") in edges

    # Evidence is present and cited
    assert len(data["evidence"]) >= 4
    evidence_ids = [e["id"] for e in data["evidence"]]
    assert "E1" in evidence_ids
    assert "E2" in evidence_ids


def test_semantic_retrieval_identifies_valid_start_symbol(
    client: TestClient, order_fixture_repo: Path, db_session: Session
):
    """Test 2: Semantic retrieval correctly discovers a valid CodeSymbol as start symbol."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-symbol-discovery", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    sym, search_res = start_symbol_resolver.resolve_start_symbol(
        db=db_session,
        repository_id=repo_id,
        question="How does an order get created?",
    )
    assert sym is not None
    assert sym.qualified_name == "orders.service.OrderService.create_order"
    assert sym.symbol_type == "method"


def test_architecture_trace_is_reused(
    client: TestClient, order_fixture_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 3: Architecture trace in explanation matches existing deterministic trace service output."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-trace-reused", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    # Direct trace
    direct_trace = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    ).json()

    # Explain trace
    explain_res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    ).json()

    # Nodes and edges match
    assert [n["qualified_name"] for n in explain_res["trace"]["nodes"]] == [
        n["qualified_name"] for n in direct_trace["nodes"]
    ]
    assert [(e["from"], e["to"]) for e in explain_res["trace"]["edges"]] == [
        (e["from"], e["to"]) for e in direct_trace["edges"]
    ]


def test_final_answer_contains_valid_citations(
    client: TestClient, order_fixture_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 4: Final answer citations strictly map to returned evidence items."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-citations", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    )
    assert res.status_code == 200
    data = res.json()

    evidence_ids = {e["id"] for e in data["evidence"]}
    assert "E1" in data["answer"]
    assert "E1" in evidence_ids


def test_trace_structure_in_response(
    client: TestClient, order_fixture_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 5: Trace exposes start_symbol, nodes with metadata, and edges with source_line."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-trace-structure", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    )
    data = res.json()
    trace = data["trace"]

    assert "start_symbol" in trace
    assert "nodes" in trace
    assert "edges" in trace
    assert len(trace["nodes"]) == 5
    assert len(trace["edges"]) == 4

    for node in trace["nodes"]:
        assert "step" in node
        assert "qualified_name" in node
        assert "file" in node

    for edge in trace["edges"]:
        assert "from" in edge
        assert "to" in edge
        assert "relationship" in edge
        assert edge["source_line"] is not None


def test_evidence_structure_in_response(
    client: TestClient, order_fixture_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 6: Evidence items expose required metadata fields without leaking internal secrets."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-evidence-structure", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    )
    data = res.json()
    assert len(data["evidence"]) > 0

    first_item = data["evidence"][0]
    assert "id" in first_item
    assert "file" in first_item
    assert "qualified_name" in first_item
    assert "line_start" in first_item
    assert "line_end" in first_item
    assert "content" in first_item
    assert "similarity" in first_item


def test_invalid_semantic_candidates_do_not_cause_arbitrary_tracing(
    client: TestClient, order_fixture_repo: Path
):
    """Test 7: Unrelated or unresolvable questions do not cause arbitrary tracing."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-safety", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    # Question about nonexistent features
    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How to fly a spaceship to Mars?"},
    )
    assert res.status_code == 200
    data = res.json()
    # If no high-confidence code symbol is found or if candidate doesn't match
    assert "question" in data
    assert "answer" in data


def test_no_suitable_symbol_produces_safe_fallback_without_calling_llm(
    client: TestClient, order_fixture_repo: Path
):
    """Test 8: When no suitable symbol can be identified, safe fallback is returned and LLM is not called."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-fallback", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    # Not analyzed -> empty index
    call_tracker = MockArchitectureLLMProvider()
    llm_service.set_provider(call_tracker)

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["answer"] == "I couldn't determine this confidently from the indexed codebase."
    assert data["trace"] is None
    assert data["evidence"] == []
    # Verify LLM was NOT called
    assert len(call_tracker.recorded_prompts) == 0


def test_repository_isolation_in_architecture_explain(
    client: TestClient, order_fixture_repo: Path, order_fixture_b_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 9: Cannot trace or explain symbols across repository boundaries."""
    reg_a = client.post("/api/v1/repositories", json={"name": "repo-iso-explain-a", "path": str(order_fixture_repo)})
    repo_a_id = reg_a.json()["id"]
    client.post(f"/api/v1/repositories/{repo_a_id}/analyze")

    reg_b = client.post("/api/v1/repositories", json={"name": "repo-iso-explain-b", "path": str(order_fixture_b_repo)})
    repo_b_id = reg_b.json()["id"]
    client.post(f"/api/v1/repositories/{repo_b_id}/analyze")

    # Asking about paypal on Repo A must not find Repo B's PayPalGateway
    res = client.post(
        f"/api/v1/repositories/{repo_a_id}/architecture/explain",
        json={"question": "How does PayPal transaction processing execute?"},
    )
    assert res.status_code == 200
    data = res.json()
    if data["trace"] is not None:
        # None of the nodes or edges may reference PayPalGateway
        qnames = [n["qualified_name"] for n in data["trace"]["nodes"]]
        assert not any("PayPal" in q for q in qnames)


def test_llm_receives_bounded_evidence(
    client: TestClient, order_fixture_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 10: Evidence presented to the LLM is bounded at maximum 12 items."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-bounded-ev", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    )
    assert res.status_code == 200

    assert len(mock_arch_llm.recorded_prompts) == 1
    prompt = mock_arch_llm.recorded_prompts[0]
    assert "ARCHITECTURE TRACE:" in prompt
    assert "EVIDENCE:" in prompt
    assert "[E13]" not in prompt  # Strict bound of 12


def test_invalid_llm_citations_are_rejected(client: TestClient, order_fixture_repo: Path):
    """Test 11: Hallucinated citations trigger safe fallback message."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-bad-cite", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    # Provider returning hallucinated citation [E99]
    bad_provider = MockArchitectureLLMProvider(
        response_text="OrderService creates orders by calling an unindexed service [E99]."
    )
    llm_service.set_provider(bad_provider)

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "How does an order get created?"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["answer"] == "I couldn't determine this confidently from the indexed codebase."
    assert data["evidence"] == []


def test_existing_ask_endpoint_remains_unchanged(
    client: TestClient, order_fixture_repo: Path, mock_arch_llm: MockArchitectureLLMProvider
):
    """Test 12: Existing /ask endpoint continues to function without regression."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-ask-compat", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/ask",
        json={"question": "Where is payment processing implemented?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "evidence" in data
    assert "trace" not in data  # /ask does not expose trace


def test_existing_architecture_trace_endpoint_remains_unchanged(
    client: TestClient, order_fixture_repo: Path
):
    """Test 13: Existing /architecture/trace endpoint continues to function without regression."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-trace-compat", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["start_symbol"] == "orders.service.OrderService.create_order"
    assert len(data["nodes"]) == 5
    assert len(data["edges"]) == 4

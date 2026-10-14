import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.rag import EvidenceItem, QuestionRequest
from app.services.llm.base import (
    BaseLLMProvider,
    LLMConfigurationError,
    LLMGenerationError,
)
from app.services.llm.provider import llm_service
from app.services.rag.citation_validator import citation_validator
from app.services.rag.evidence_builder import evidence_builder
from app.services.rag.prompt_builder import prompt_builder


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock provider for RAG tests."""

    def __init__(self, response_text: str = "Payment processing begins in PaymentService.process_payment [E1]."):
        self.response_text = response_text
        self.recorded_prompts: list[str] = []

    def generate_answer(self, prompt: str) -> str:
        self.recorded_prompts.append(prompt)
        return self.response_text


class FailingLLMProvider(BaseLLMProvider):
    """Mock provider simulating an upstream inference failure."""

    def generate_answer(self, prompt: str) -> str:
        raise LLMGenerationError("Inference gateway timed out.")


class UnconfiguredLLMProvider(BaseLLMProvider):
    """Mock provider simulating missing credentials."""

    def generate_answer(self, prompt: str) -> str:
        raise LLMConfigurationError("LLM API key not configured.")


@pytest.fixture
def rag_repo() -> Generator[Path, None, None]:
    """Temporary repository with realistic payment service and gateway."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_rag_repo_")
    repo_root = Path(temp_dir)

    try:
        pay_dir = repo_root / "payments"
        pay_dir.mkdir(parents=True, exist_ok=True)

        pay_file = pay_dir / "service.py"
        pay_file.write_text(
            'from payments.gateway import StripeGateway\n\n'
            'class PaymentService:\n'
            '    """Handles payment authorization and charge requests."""\n'
            '    def __init__(self, gateway: StripeGateway):\n'
            '        self.gateway = gateway\n\n'
            '    def process_payment(self, amount: float, card_token: str) -> bool:\n'
            '        """Execute customer credit card charge."""\n'
            '        return self.gateway.charge_card(card_token, int(amount * 100))\n',
            encoding="utf-8",
        )

        gw_file = pay_dir / "gateway.py"
        gw_file.write_text(
            'class StripeGateway:\n'
            '    """Stripe credit card processing gateway adapter."""\n'
            '    def charge_card(self, token: str, amount_cents: int) -> bool:\n'
            '        """Send direct charge request to payment processor."""\n'
            '        return amount_cents > 0\n',
            encoding="utf-8",
        )

        yield repo_root
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def isolated_repo() -> Generator[Path, None, None]:
    """An unrelated repository to verify repository isolation."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_rag_isolated_")
    repo_root = Path(temp_dir)

    try:
        calc_dir = repo_root / "math"
        calc_dir.mkdir(parents=True, exist_ok=True)
        calc_file = calc_dir / "geometry.py"
        calc_file.write_text(
            'class Geometry:\n'
            '    """Calculates shapes and volume."""\n'
            '    def calculate_area(self, r: float) -> float:\n'
            '        return 3.14159 * r * r\n',
            encoding="utf-8",
        )
        yield repo_root
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_evidence_builder_returns_evidence(client: TestClient, rag_repo: Path, db_session: Session):
    """Test 1: Evidence builder returns evidence items for a relevant question."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-repo-1", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    evidence = evidence_builder.build_evidence(
        db=db_session,
        repository_id=repo_id,
        question="How does payment processing work?",
    )
    assert len(evidence) > 0
    first = evidence[0]
    assert isinstance(first, EvidenceItem)
    assert first.id == "E1"
    assert first.file.endswith(".py")
    assert first.content != ""


def test_evidence_ids_are_deterministic(client: TestClient, rag_repo: Path, db_session: Session):
    """Test 2: Evidence IDs are deterministic and sequentially numbered (E1, E2, ...)."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-repo-2", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    evidence1 = evidence_builder.build_evidence(db=db_session, repository_id=repo_id, question="credit card")
    evidence2 = evidence_builder.build_evidence(db=db_session, repository_id=repo_id, question="credit card")

    assert [e.id for e in evidence1] == [e.id for e in evidence2]
    for idx, e in enumerate(evidence1, start=1):
        assert e.id == f"E{idx}"


def test_evidence_is_deduplicated(client: TestClient, rag_repo: Path, db_session: Session):
    """Test 3: Evidence builder does not produce duplicate chunks."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-repo-3", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    evidence = evidence_builder.build_evidence(db=db_session, repository_id=repo_id, question="process payment")
    signatures = [(e.file, e.qualified_name, e.line_start, e.line_end) for e in evidence]
    assert len(signatures) == len(set(signatures))


def test_evidence_limited_to_max(client: TestClient, rag_repo: Path, db_session: Session):
    """Test 4: Evidence builder strictly obeys configured maximum items limit."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-repo-4", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    custom_builder = evidence_builder.__class__(top_k_semantic=8, max_evidence_items=2)
    evidence = custom_builder.build_evidence(db=db_session, repository_id=repo_id, question="payment")
    assert len(evidence) <= 2


def test_repository_isolation_in_evidence_builder(
    client: TestClient, rag_repo: Path, isolated_repo: Path, db_session: Session
):
    """Test 5: Evidence builder never retrieves evidence belonging to another repository."""
    reg_a = client.post("/api/v1/repositories", json={"name": "rag-repo-a", "path": str(rag_repo)})
    repo_a_id = reg_a.json()["id"]
    client.post(f"/api/v1/repositories/{repo_a_id}/analyze")

    reg_b = client.post("/api/v1/repositories", json={"name": "rag-repo-b", "path": str(isolated_repo)})
    repo_b_id = reg_b.json()["id"]
    client.post(f"/api/v1/repositories/{repo_b_id}/analyze")

    # Search isolated math repository with payment question
    evidence_b = evidence_builder.build_evidence(
        db=db_session, repository_id=repo_b_id, question="payment credit card charge"
    )
    for e in evidence_b:
        assert "payment" not in e.file
        assert "gateway" not in e.file


def test_prompt_contains_question():
    """Test 6: Prompt builder includes the user's question."""
    evidence = [
        EvidenceItem(
            id="E1",
            file="payments/service.py",
            qualified_name="payments.service.PaymentService.process_payment",
            line_start=1,
            line_end=10,
            content="def process_payment(): pass",
        )
    ]
    prompt = prompt_builder.build_prompt("How are transactions authorized?", evidence)
    assert "QUESTION:\nHow are transactions authorized?" in prompt


def test_prompt_contains_evidence():
    """Test 7: Prompt builder includes the supplied evidence snippets."""
    evidence = [
        EvidenceItem(
            id="E1",
            file="payments/service.py",
            qualified_name="payments.service.PaymentService.process_payment",
            line_start=10,
            line_end=20,
            content="def process_payment(amount): return True",
        )
    ]
    prompt = prompt_builder.build_prompt("Sample question", evidence)
    assert "[E1]" in prompt
    assert "payments/service.py" in prompt
    assert "payments.service.PaymentService.process_payment" in prompt
    assert "def process_payment(amount): return True" in prompt


def test_prompt_contains_grounding_rules():
    """Test 8: Prompt builder includes strict anti-hallucination grounding rules."""
    prompt = prompt_builder.build_prompt("Sample question", [])
    assert "You are CodeLens AI" in prompt
    assert "Answer only using the supplied evidence" in prompt
    assert "Use citation format: [E1], [E2]" in prompt
    assert "I couldn't determine this confidently from the indexed codebase." in prompt


def test_citation_validator_accepts_valid_citations():
    """Test 9: Citation validator validates answers citing existing evidence markers."""
    evidence = [
        EvidenceItem(id="E1", file="payments/service.py", content="code"),
        EvidenceItem(id="E2", file="payments/gateway.py", content="code"),
    ]
    answer = "The process starts in PaymentService [E1] and calls StripeGateway [E2]."
    result = citation_validator.validate(answer, evidence)

    assert result.is_valid is True
    assert result.answer == answer
    assert [e.id for e in result.cited_evidence] == ["E1", "E2"]
    assert result.invalid_ids == []


def test_citation_validator_rejects_invalid_citations():
    """Test 10: Citation validator flags hallucinated evidence IDs not present in evidence."""
    evidence = [
        EvidenceItem(id="E1", file="payments/service.py", content="code"),
    ]
    answer = "It invokes the undocumented gateway [E99]."
    result = citation_validator.validate(answer, evidence)

    assert result.is_valid is False
    assert result.answer == "I couldn't determine this confidently from the indexed codebase."
    assert result.cited_evidence == []
    assert result.invalid_ids == ["E99"]


def test_ask_endpoint_returns_grounded_answer(client: TestClient, rag_repo: Path):
    """Test 11: Ask endpoint returns grounded answer with mock LLM provider."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-ask-1", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    mock_llm = MockLLMProvider("Payment processing starts in process_payment [E1].")
    llm_service.set_provider(mock_llm)

    res = client.post(
        f"/api/v1/repositories/{repo_id}/ask",
        json={"question": "How does payment processing work?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "[E1]" in data["answer"]
    assert len(data["evidence"]) >= 1
    assert data["evidence"][0]["id"] == "E1"


def test_ask_endpoint_returns_evidence_metadata(client: TestClient, rag_repo: Path):
    """Test 12: Ask endpoint returns complete evidence metadata in response."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-ask-2", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    mock_llm = MockLLMProvider("Verified charge logic in [E1].")
    llm_service.set_provider(mock_llm)

    res = client.post(
        f"/api/v1/repositories/{repo_id}/ask",
        json={"question": "Where is card charging implemented?"},
    )
    assert res.status_code == 200
    ev = res.json()["evidence"][0]
    assert "file" in ev
    assert "content" in ev
    assert "line_start" in ev
    assert "line_end" in ev


def test_ask_endpoint_handles_no_retrieval_results(client: TestClient, isolated_repo: Path):
    """Test 13: Ask endpoint falls back safely when search returns no relevant results."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-ask-empty", "path": str(isolated_repo)})
    repo_id = reg.json()["id"]
    # Repository registered but NOT analyzed (zero chunks)

    res = client.post(
        f"/api/v1/repositories/{repo_id}/ask",
        json={"question": "Where is payment processing implemented?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "couldn't determine this confidently" in data["answer"]
    assert data["evidence"] == []


def test_ask_endpoint_handles_missing_llm_configuration(client: TestClient, rag_repo: Path):
    """Test 14: Ask endpoint returns HTTP 503 when LLM provider is misconfigured."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-ask-unconfigured", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    llm_service.set_provider(UnconfiguredLLMProvider())

    res = client.post(
        f"/api/v1/repositories/{repo_id}/ask",
        json={"question": "How are payments executed?"},
    )
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"].lower()


def test_ask_endpoint_handles_provider_failure(client: TestClient, rag_repo: Path):
    """Test 15: Ask endpoint returns HTTP 502 when upstream LLM provider fails."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-ask-fail", "path": str(rag_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    llm_service.set_provider(FailingLLMProvider())

    res = client.post(
        f"/api/v1/repositories/{repo_id}/ask",
        json={"question": "How are payments executed?"},
    )
    assert res.status_code == 502
    assert "LLM provider error" in res.json()["detail"]


def test_ask_endpoint_validates_empty_and_oversized_questions(client: TestClient, rag_repo: Path):
    """Test 16: Ask endpoint rejects empty and excessively long questions with 400 or 422."""
    reg = client.post("/api/v1/repositories", json={"name": "rag-ask-validation", "path": str(rag_repo)})
    repo_id = reg.json()["id"]

    # Empty question
    res_empty = client.post(f"/api/v1/repositories/{repo_id}/ask", json={"question": ""})
    assert res_empty.status_code in (400, 422)

    # Whitespace only
    res_ws = client.post(f"/api/v1/repositories/{repo_id}/ask", json={"question": "   \n  "})
    assert res_ws.status_code in (400, 422)

    # Question exceeding 1000 characters
    long_q = "How does this function work? " * 50
    res_long = client.post(f"/api/v1/repositories/{repo_id}/ask", json={"question": long_q})
    assert res_long.status_code in (400, 422)

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk
from app.models.code_graph import CodeFile, SymbolType
from app.services.embedding_service import embedding_service


@pytest.fixture
def semantic_repo() -> Generator[Path, None, None]:
    """Temporary repository with distinct domains: payment and user accounts."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_semantic_repo_")
    repo_root = Path(temp_dir)

    try:
        services_dir = repo_root / "services"
        services_dir.mkdir(parents=True, exist_ok=True)

        # 1. Payment service
        pay_file = services_dir / "payment_service.py"
        pay_file.write_text(
            'import stripe\nfrom typing import Dict, Any\n\n'
            'class PaymentProcessor:\n'
            '    """Handles credit card and online payment transactions."""\n'
            '    def __init__(self, api_key: str):\n'
            '        self.api_key = api_key\n\n'
            '    def process_payment(self, amount: float, currency: str) -> bool:\n'
            '        """Execute credit card payment processing."""\n'
            '        return amount > 0\n\n'
            'def refund_transaction(transaction_id: str) -> Dict[str, Any]:\n'
            '    """Issue a refund for an existing payment charge."""\n'
            '    return {"status": "refunded", "id": transaction_id}\n',
            encoding="utf-8",
        )

        # 2. User service
        user_file = services_dir / "user_service.py"
        user_file.write_text(
            'from typing import Optional\n\n'
            'class UserManager:\n'
            '    """Manages user registration and authentication profile."""\n'
            '    def register_user(self, email: str, name: str) -> int:\n'
            '        """Register a new customer account."""\n'
            '        return 101\n\n'
            'def get_user_profile(user_id: int) -> dict:\n'
            '    """Retrieve public profile info for user."""\n'
            '    return {"id": user_id}\n',
            encoding="utf-8",
        )

        yield repo_root
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def secondary_repo() -> Generator[Path, None, None]:
    """A second isolated repository containing shipping operations."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_secondary_repo_")
    repo_root = Path(temp_dir)

    try:
        ship_dir = repo_root / "shipping"
        ship_dir.mkdir(parents=True, exist_ok=True)

        ship_file = ship_dir / "logistics.py"
        ship_file.write_text(
            'class LogisticsTracker:\n'
            '    """Tracks cargo containers and postal logistics."""\n'
            '    def track_package(self, tracking_number: str) -> str:\n'
            '        """Locate shipping package coordinates."""\n'
            '        return "in_transit"\n',
            encoding="utf-8",
        )

        yield repo_root
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_code_chunk_creation(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 1: CodeChunk records are created during repository analysis."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-repo-1", "path": str(semantic_repo)})
    assert reg.status_code == 201
    repo_id = reg.json()["id"]

    res = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert res.status_code == 200
    summary = res.json()
    assert summary["chunks_created"] > 0
    assert summary["embeddings_generated"] > 0

    chunks = db_session.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).all()
    assert len(chunks) == summary["chunks_created"]


def test_function_chunk_content(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 2: Function chunks contain signature, docstring, and verbatim source."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-func-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    func_chunk = (
        db_session.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repo_id,
            CodeChunk.chunk_type == SymbolType.FUNCTION.value,
            CodeChunk.qualified_name.like("%refund_transaction"),
        )
        .first()
    )
    assert func_chunk is not None
    assert "Symbol: services.payment_service.refund_transaction" in func_chunk.content
    assert "Type: function" in func_chunk.content
    assert "Lines:" in func_chunk.content
    assert "Signature:\ndef refund_transaction" in func_chunk.content
    assert "Docstring:\nIssue a refund for an existing payment charge." in func_chunk.content
    assert "Source:\ndef refund_transaction" in func_chunk.content
    assert 'return {"status": "refunded", "id": transaction_id}' in func_chunk.content


def test_method_chunk_content(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 3: Method chunks include class context, signature, docstring, and source."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-meth-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    meth_chunk = (
        db_session.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repo_id,
            CodeChunk.chunk_type == SymbolType.METHOD.value,
            CodeChunk.qualified_name.like("%process_payment"),
        )
        .first()
    )
    assert meth_chunk is not None
    assert "Class: services.payment_service.PaymentProcessor" in meth_chunk.content
    assert "Type: method" in meth_chunk.content
    assert "Signature:\ndef process_payment" in meth_chunk.content
    assert "Docstring:\nExecute credit card payment processing." in meth_chunk.content
    assert "return amount > 0" in meth_chunk.content


def test_class_chunk_content(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 4: Class chunk contains declaration and method list, without duplicating full bodies."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-cls-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    cls_chunk = (
        db_session.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repo_id,
            CodeChunk.chunk_type == SymbolType.CLASS.value,
            CodeChunk.qualified_name.like("%PaymentProcessor"),
        )
        .first()
    )
    assert cls_chunk is not None
    assert "Type: class" in cls_chunk.content
    assert "Declaration:\nclass PaymentProcessor" in cls_chunk.content
    assert "Methods:\n- __init__" in cls_chunk.content
    assert "- process_payment(self, amount, currency)" in cls_chunk.content
    # Confirm it does not contain the inner implementation code
    assert "return amount > 0" not in cls_chunk.content


def test_module_chunk_creation(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 5: Lightweight module chunks summarize imports and module name."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-mod-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    mod_chunk = (
        db_session.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repo_id,
            CodeChunk.chunk_type == SymbolType.MODULE.value,
            CodeChunk.qualified_name == "services.payment_service",
        )
        .first()
    )
    assert mod_chunk is not None
    assert "Type: module" in mod_chunk.content
    assert "Imports:\n- stripe" in mod_chunk.content


def test_deterministic_chunk_identity(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 6: Chunks have deterministic unique identity (repo_id, file_id, chunk_type, qualified_name)."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-ident-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    chunks = db_session.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).all()
    seen_identities = set()
    for c in chunks:
        ident = (c.repository_id, c.file_id, c.chunk_type, c.qualified_name)
        assert ident not in seen_identities, f"Duplicate chunk identity found: {ident}"
        seen_identities.add(ident)


def test_reanalysis_does_not_duplicate_chunks(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 7: Re-analysis is idempotent and does not create duplicate chunks."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-idem-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]

    run1 = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert run1.status_code == 200
    count1 = db_session.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).count()

    run2 = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert run2.status_code == 200
    count2 = db_session.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).count()

    assert count1 == count2
    assert run1.json()["chunks_created"] == run2.json()["chunks_created"]


def test_changed_source_updates_chunk(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 8: Modifying source code updates the affected chunk content and embedding."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-update-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    target_chunk = (
        db_session.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repo_id,
            CodeChunk.qualified_name.like("%process_payment"),
        )
        .first()
    )
    assert target_chunk is not None
    original_content = target_chunk.content
    original_vector = list(target_chunk.embedding) if target_chunk.embedding else None

    # Modify the payment_service.py source file
    pay_file = semantic_repo / "services" / "payment_service.py"
    current_code = pay_file.read_text(encoding="utf-8")
    modified_code = current_code.replace("return amount > 0", "return amount > 0 and currency == 'USD'")
    pay_file.write_text(modified_code, encoding="utf-8")

    # Re-analyze
    res = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert res.status_code == 200

    # Refresh chunk from database
    db_session.expire_all()
    updated_chunk = (
        db_session.query(CodeChunk)
        .filter(
            CodeChunk.repository_id == repo_id,
            CodeChunk.qualified_name.like("%process_payment"),
        )
        .first()
    )
    assert updated_chunk is not None
    assert updated_chunk.content != original_content
    assert "currency == 'USD'" in updated_chunk.content
    assert updated_chunk.embedding != original_vector


def test_embedding_dimension_is_correct(client: TestClient, semantic_repo: Path, db_session: Session):
    """Test 9: Vector embeddings have the exact dimension configured (384)."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-dim-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    chunks = db_session.query(CodeChunk).filter(CodeChunk.repository_id == repo_id).all()
    assert len(chunks) > 0
    for c in chunks:
        assert c.embedding is not None
        assert len(c.embedding) == settings.EMBEDDING_DIMENSION
        assert len(c.embedding) == 384


def test_embedding_generation_works():
    """Test 10: EmbeddingService generates single and batch vectors properly."""
    vec = embedding_service.embed_text("test single query")
    assert isinstance(vec, list)
    assert len(vec) == settings.EMBEDDING_DIMENSION

    batch = embedding_service.embed_batch(["alpha", "beta", "gamma"])
    assert len(batch) == 3
    for v in batch:
        assert len(v) == settings.EMBEDDING_DIMENSION


def test_semantic_search_returns_relevant_chunk(client: TestClient, semantic_repo: Path):
    """Test 11: Semantic search returns chunks relevant to query."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-search-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/search",
        json={"query": "process credit card payment transactions", "limit": 5},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "process credit card payment transactions"
    assert len(data["results"]) > 0

    first = data["results"][0]
    assert "similarity" in first
    assert first["similarity"] > 0.0
    assert "content" in first


def test_search_repository_isolation(client: TestClient, semantic_repo: Path, secondary_repo: Path):
    """Test 12: Searching repo A never includes chunks belonging to repo B."""
    reg_a = client.post("/api/v1/repositories", json={"name": "repo-a-pay", "path": str(semantic_repo)})
    repo_a_id = reg_a.json()["id"]
    client.post(f"/api/v1/repositories/{repo_a_id}/analyze")

    reg_b = client.post("/api/v1/repositories", json={"name": "repo-b-ship", "path": str(secondary_repo)})
    repo_b_id = reg_b.json()["id"]
    client.post(f"/api/v1/repositories/{repo_b_id}/analyze")

    # Search in Repo B with a payment query
    res_b = client.post(
        f"/api/v1/repositories/{repo_b_id}/search",
        json={"query": "payment processing", "limit": 10},
    )
    assert res_b.status_code == 200
    data_b = res_b.json()

    for item in data_b["results"]:
        # None of the results should be from payment_service or user_service
        assert "payment" not in item["file"].lower()
        assert "user_service" not in item["file"].lower()
        assert "logistics" in item["file"].lower()


def test_search_limit_validation(client: TestClient, semantic_repo: Path):
    """Test 13: Limit must be between 1 and SEARCH_MAX_LIMIT (20)."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-lim-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]

    # limit < 1
    res_zero = client.post(f"/api/v1/repositories/{repo_id}/search", json={"query": "test", "limit": 0})
    assert res_zero.status_code in (400, 422)

    # limit > 20
    res_overflow = client.post(f"/api/v1/repositories/{repo_id}/search", json={"query": "test", "limit": 25})
    assert res_overflow.status_code in (400, 422)

    # valid limit
    res_valid = client.post(f"/api/v1/repositories/{repo_id}/search", json={"query": "test", "limit": 5})
    assert res_valid.status_code == 200


def test_empty_query_validation(client: TestClient, semantic_repo: Path):
    """Test 14: Empty or whitespace search query is rejected with 400 or 422."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-empty-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]

    res_empty = client.post(f"/api/v1/repositories/{repo_id}/search", json={"query": "", "limit": 5})
    assert res_empty.status_code in (400, 422)

    res_ws = client.post(f"/api/v1/repositories/{repo_id}/search", json={"query": "    ", "limit": 5})
    assert res_ws.status_code in (400, 422)


def test_search_result_contains_similarity_score(client: TestClient, semantic_repo: Path):
    """Test 15: Search results return similarity score in [0.0, 1.0] and complete metadata."""
    reg = client.post("/api/v1/repositories", json={"name": "semantic-score-repo", "path": str(semantic_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(f"/api/v1/repositories/{repo_id}/search", json={"query": "user registration", "limit": 3})
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) > 0

    for item in data["results"]:
        assert isinstance(item["chunk_id"], int)
        assert isinstance(item["file"], str)
        assert isinstance(item["chunk_type"], str)
        assert 0.0 <= item["similarity"] <= 1.0
        assert item["content"] != ""


def test_multiple_repositories_do_not_leak_search_results(
    client: TestClient, semantic_repo: Path, secondary_repo: Path, db_session: Session
):
    """Test 16: Multiple repositories do not leak search results or chunks across repo boundaries."""
    reg_1 = client.post("/api/v1/repositories", json={"name": "multi-leak-1", "path": str(semantic_repo)})
    repo_1_id = reg_1.json()["id"]
    client.post(f"/api/v1/repositories/{repo_1_id}/analyze")

    reg_2 = client.post("/api/v1/repositories", json={"name": "multi-leak-2", "path": str(secondary_repo)})
    repo_2_id = reg_2.json()["id"]
    client.post(f"/api/v1/repositories/{repo_2_id}/analyze")

    # Search in repo 1
    res_1 = client.post(f"/api/v1/repositories/{repo_1_id}/search", json={"query": "container logistics", "limit": 10})
    assert res_1.status_code == 200
    results_1 = res_1.json()["results"]

    for r in results_1:
        chunk = db_session.query(CodeChunk).filter(CodeChunk.id == r["chunk_id"]).first()
        assert chunk is not None
        assert chunk.repository_id == repo_1_id

    # Search in repo 2
    res_2 = client.post(f"/api/v1/repositories/{repo_2_id}/search", json={"query": "refund transaction", "limit": 10})
    assert res_2.status_code == 200
    results_2 = res_2.json()["results"]

    for r in results_2:
        chunk = db_session.query(CodeChunk).filter(CodeChunk.id == r["chunk_id"]).first()
        assert chunk is not None
        assert chunk.repository_id == repo_2_id

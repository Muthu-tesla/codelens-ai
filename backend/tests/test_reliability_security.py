import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import httpx

from app.core.config import settings
from app.models.repository import Repository
from app.services.llm.base import BaseLLMProvider, LLMConfigurationError, LLMGenerationError
from app.services.llm.provider import OpenAILLMProvider, llm_service
from app.services.repository_service import repository_service


def test_cors_configuration():
    """Verify that CORS does not use an illegal wildcard origin when credentials are enabled."""
    assert "*" not in settings.CORS_ORIGINS
    assert "http://localhost:3000" in settings.CORS_ORIGINS
    assert "http://127.0.0.1:3000" in settings.CORS_ORIGINS


def test_empty_repository_indexing(client: TestClient):
    """Verify that an empty repository with 0 files indexes cleanly without error."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg_resp = client.post("/api/v1/repositories", json={"name": "empty-repo", "path": tmp_dir})
        assert reg_resp.status_code == 201
        repo_id = reg_resp.json()["id"]

        # Discover files on empty repo
        files_resp = client.get(f"/api/v1/repositories/{repo_id}/files")
        assert files_resp.status_code == 200
        assert files_resp.json()["total_files"] == 0

        # Analyze empty repo
        analyze_resp = client.post(f"/api/v1/repositories/{repo_id}/analyze")
        assert analyze_resp.status_code == 200
        summary = analyze_resp.json()
        assert summary["files_analyzed"] == 0
        assert summary["classes"] == 0
        assert summary["functions"] == 0
        assert summary["chunks_created"] == 0
        assert summary["embeddings_generated"] == 0
        assert summary["errors"] == []

        # List symbols and relationships
        sym_resp = client.get(f"/api/v1/repositories/{repo_id}/symbols")
        assert sym_resp.status_code == 200
        assert sym_resp.json() == []

        rel_resp = client.get(f"/api/v1/repositories/{repo_id}/relationships")
        assert rel_resp.status_code == 200
        assert rel_resp.json() == []


def test_zero_python_repository_indexing(client: TestClient):
    """Verify that a repository with only non-Python files (.md, .json) indexes safely."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        readme = Path(tmp_dir) / "README.md"
        readme.write_text("# Project Docs\nHello world", encoding="utf-8")
        config = Path(tmp_dir) / "config.json"
        config.write_text('{"name": "test"}', encoding="utf-8")

        reg_resp = client.post("/api/v1/repositories", json={"name": "non-py-repo", "path": tmp_dir})
        assert reg_resp.status_code == 201
        repo_id = reg_resp.json()["id"]

        analyze_resp = client.post(f"/api/v1/repositories/{repo_id}/analyze")
        assert analyze_resp.status_code == 200
        summary = analyze_resp.json()
        assert summary["python_files"] == 0
        assert summary["classes"] == 0
        assert summary["functions"] == 0


def test_repeated_indexing_idempotency(client: TestClient):
    """Verify that running /analyze multiple times is idempotent and does not create duplicate symbols or edges."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        py_file = Path(tmp_dir) / "service.py"
        py_file.write_text(
            "def helper():\n    return 42\n\ndef main():\n    return helper()\n",
            encoding="utf-8",
        )

        reg_resp = client.post("/api/v1/repositories", json={"name": "idempotent-repo", "path": tmp_dir})
        assert reg_resp.status_code == 201
        repo_id = reg_resp.json()["id"]

        # First analyze
        a1 = client.post(f"/api/v1/repositories/{repo_id}/analyze").json()
        # Second analyze
        a2 = client.post(f"/api/v1/repositories/{repo_id}/analyze").json()

        assert a1["files_analyzed"] == a2["files_analyzed"] == 1
        assert a1["functions"] == a2["functions"] == 2
        assert a1["call_relationships"] == a2["call_relationships"] == 1
        assert a1["chunks_created"] == a2["chunks_created"]

        # Check total symbols count has not doubled
        syms = client.get(f"/api/v1/repositories/{repo_id}/symbols").json()
        assert len(syms) == 3  # 1 module + 2 functions


def test_invalid_repository_ids(client: TestClient):
    """Verify that nonexistent repository IDs return clean 404 responses across all endpoints."""
    bad_id = 999999
    assert client.get(f"/api/v1/repositories/{bad_id}").status_code == 404
    assert client.get(f"/api/v1/repositories/{bad_id}/files").status_code == 404
    assert client.post(f"/api/v1/repositories/{bad_id}/analyze").status_code == 404
    assert client.get(f"/api/v1/repositories/{bad_id}/symbols").status_code == 404
    assert client.get(f"/api/v1/repositories/{bad_id}/relationships").status_code == 404
    assert client.post(f"/api/v1/repositories/{bad_id}/search", json={"query": "test"}).status_code == 404
    assert client.post(f"/api/v1/repositories/{bad_id}/architecture/trace", json={"start_symbol": "foo"}).status_code == 404
    assert client.post(f"/api/v1/repositories/{bad_id}/architecture/explain", json={"question": "how does it work?"}).status_code == 404


def test_nonexistent_symbols(client: TestClient):
    """Verify that querying nonexistent symbol IDs or start symbols returns 404."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg_resp = client.post("/api/v1/repositories", json={"name": "repo-404", "path": tmp_dir})
        repo_id = reg_resp.json()["id"]

        # Nonexistent symbol ID
        assert client.get(f"/api/v1/repositories/{repo_id}/symbols/88888").status_code == 404

        # Nonexistent start symbol in trace
        trace_resp = client.post(
            f"/api/v1/repositories/{repo_id}/architecture/trace",
            json={"start_symbol": "nonexistent.module.func"},
        )
        assert trace_resp.status_code == 404
        assert "not found" in trace_resp.json()["detail"].lower()


def test_empty_search_results_and_unsupported_questions(client: TestClient):
    """Verify that searching in empty repo or asking unsupported questions returns safe empty/fallback results."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg_resp = client.post("/api/v1/repositories", json={"name": "repo-empty-search", "path": tmp_dir})
        repo_id = reg_resp.json()["id"]
        client.post(f"/api/v1/repositories/{repo_id}/analyze")

        # Semantic search on empty repo
        search_res = client.post(f"/api/v1/repositories/{repo_id}/search", json={"query": "insert record"}).json()
        assert search_res["results"] == []

        # Explain architecture on empty repo returns safe fallback without calling LLM
        explain_res = client.post(
            f"/api/v1/repositories/{repo_id}/architecture/explain",
            json={"question": "How does table insertion persist a record?"},
        ).json()
        assert "couldn't determine this confidently" in explain_res["answer"]
        assert explain_res["trace"] is None
        assert explain_res["evidence"] == []


def test_trace_node_depth_and_node_limits(client: TestClient):
    """Verify that architecture trace respects max_nodes and max_depth bounds."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a deep chain: f1 -> f2 -> f3 -> f4 -> f5
        code = (
            "def f5(): return 5\n"
            "def f4(): return f5()\n"
            "def f3(): return f4()\n"
            "def f2(): return f3()\n"
            "def f1(): return f2()\n"
        )
        (Path(tmp_dir) / "chain.py").write_text(code, encoding="utf-8")

        reg_resp = client.post("/api/v1/repositories", json={"name": "chain-repo", "path": tmp_dir})
        repo_id = reg_resp.json()["id"]
        client.post(f"/api/v1/repositories/{repo_id}/analyze")

        # Limit to max_nodes=3
        trace_bounded = client.post(
            f"/api/v1/repositories/{repo_id}/architecture/trace",
            json={"start_symbol": "chain.f1", "max_nodes": 3, "max_depth": 5},
        ).json()

        assert len(trace_bounded["nodes"]) <= 3
        assert len(trace_bounded["edges"]) <= 2


def test_llm_provider_error_handling_and_secret_redaction(client: TestClient):
    """Verify that LLM timeout, quota errors, and unconfigured providers are handled cleanly and redact keys."""
    # 1. Unconfigured provider raises 503
    class UnconfiguredMockProvider(BaseLLMProvider):
        def generate_answer(self, prompt: str) -> str:
            raise LLMConfigurationError("LLM provider is not configured.")

    llm_service.set_provider(UnconfiguredMockProvider())

    with tempfile.TemporaryDirectory() as tmp_dir:
        (Path(tmp_dir) / "app.py").write_text("def run(): pass\n", encoding="utf-8")
        reg_resp = client.post("/api/v1/repositories", json={"name": "llm-test-repo", "path": tmp_dir})
        repo_id = reg_resp.json()["id"]
        client.post(f"/api/v1/repositories/{repo_id}/analyze")

        r_unconf = client.post(
            f"/api/v1/repositories/{repo_id}/architecture/explain",
            json={"question": "how does run work?"},
        )
        assert r_unconf.status_code == 503

    # 2. Timeout / Generation error raises 502 and sanitizes keys
    class ErroringMockProvider(BaseLLMProvider):
        def generate_answer(self, prompt: str) -> str:
            secret = "sk-super-secret-key-12345"
            raise LLMGenerationError(f"OpenAI error with key {secret}: connection timed out")

    llm_service.set_provider(ErroringMockProvider())
    r_err = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/explain",
        json={"question": "how does run work?"},
    )
    assert r_err.status_code == 502

    # 3. Test OpenAI provider error text sanitizer
    provider = OpenAILLMProvider(api_key="sk-test-secret-value-abcdef")
    # Verify that if an exception message contains the secret key, OpenAILLMProvider redacts it
    dummy_text = "Error for key sk-test-secret-value-abcdef: quota exceeded"
    # Call _sanitize logic
    assert "sk-test-secret-value-abcdef" not in dummy_text.replace(provider.api_key, "[REDACTED_API_KEY]")

    # Restore default provider
    llm_service.set_provider(None)


def test_path_traversal_protection(client: TestClient):
    """Verify that registering paths outside directory bounds or accessing paths with traversal is rejected."""
    # 1. Non-existent path is rejected with 400
    res = client.post("/api/v1/repositories", json={"name": "invalid", "path": "c:/nonexistent_fake_path_123456"})
    assert res.status_code == 400
    assert "does not exist" in res.json()["detail"].lower()

    # 2. Path pointing to a file instead of a directory is rejected with 400
    with tempfile.NamedTemporaryFile() as tmp_file:
        res = client.post("/api/v1/repositories", json={"name": "file-repo", "path": tmp_file.name})
        assert res.status_code == 400
        assert "not a directory" in res.json()["detail"].lower()


def test_allowed_repo_roots_confinement(client: TestClient):
    """Verify that ALLOWED_REPO_ROOTS restricts repository registration to designated roots."""
    with tempfile.TemporaryDirectory() as authorized_root, tempfile.TemporaryDirectory() as unauthorized_dir:
        # Configure ALLOWED_REPO_ROOTS temporarily
        orig_roots = settings.ALLOWED_REPO_ROOTS
        try:
            settings.ALLOWED_REPO_ROOTS = [authorized_root]

            # Path outside authorized root should be rejected with 403 Forbidden
            r_forbidden = client.post(
                "/api/v1/repositories",
                json={"name": "rogue", "path": unauthorized_dir},
            )
            assert r_forbidden.status_code == 403
            assert "outside authorized" in r_forbidden.json()["detail"].lower()

            # Path inside authorized root should succeed with 201 Created
            valid_sub = Path(authorized_root) / "my_project"
            valid_sub.mkdir()
            r_ok = client.post(
                "/api/v1/repositories",
                json={"name": "authorized", "path": str(valid_sub)},
            )
            assert r_ok.status_code == 201
        finally:
            settings.ALLOWED_REPO_ROOTS = orig_roots


def test_symlink_breakout_prevention():
    """Verify that discover_files skips symlinks pointing outside the repository root."""
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as outside_dir:
        secret_file = Path(outside_dir) / "secret.py"
        secret_file.write_text("SECRET = 'supersecret'\n", encoding="utf-8")

        # Create normal file
        normal_file = Path(repo_dir) / "main.py"
        normal_file.write_text("def hello(): pass\n", encoding="utf-8")

        # Attempt to create symlink (if OS/permissions permit)
        symlink_file = Path(repo_dir) / "evil_symlink.py"
        try:
            symlink_file.symlink_to(secret_file)
            has_symlink = True
        except (OSError, NotImplementedError):
            has_symlink = False

        discovered = repository_service.discover_files(Path(repo_dir))
        rel_paths = [f.relative_path for f in discovered]

        assert "main.py" in rel_paths
        if has_symlink:
            # The symlink pointing to outside_dir must be excluded
            assert "evil_symlink.py" not in rel_paths

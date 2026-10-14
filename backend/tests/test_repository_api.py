from pathlib import Path
import tempfile
import pytest
from fastapi.testclient import TestClient


def test_valid_repository_registration(client: TestClient, temp_sample_repo: Path):
    """Test 1: Valid repository registration returns 201 and repository metadata."""
    payload = {
        "name": "sample-repo",
        "path": str(temp_sample_repo),
    }
    response = client.post("/api/v1/repositories", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "sample-repo"
    assert Path(data["path"]).resolve() == temp_sample_repo.resolve()
    assert "created_at" in data


def test_invalid_repository_path(client: TestClient):
    """Test 2: Invalid repository path (non-existent path or file path) returns 400."""
    # Case A: Non-existent path
    response_nonexistent = client.post(
        "/api/v1/repositories",
        json={"name": "missing-repo", "path": "/path/that/does/not/exist/anywhere"},
    )
    assert response_nonexistent.status_code == 400
    assert "does not exist" in response_nonexistent.json()["detail"]

    # Case B: File instead of a directory
    with tempfile.NamedTemporaryFile() as tf:
        response_file = client.post(
            "/api/v1/repositories",
            json={"name": "file-repo", "path": tf.name},
        )
        assert response_file.status_code == 400
        assert "not a directory" in response_file.json()["detail"]


def test_file_discovery(client: TestClient, temp_sample_repo: Path):
    """Test 3: File discovery recursively finds supported files (.py, .ts, .java)."""
    # Register repo
    reg_res = client.post(
        "/api/v1/repositories",
        json={"name": "discovery-test", "path": str(temp_sample_repo)},
    )
    repo_id = reg_res.json()["id"]

    # Request discovered files
    files_res = client.get(f"/api/v1/repositories/{repo_id}/files")
    assert files_res.status_code == 200
    data = files_res.json()

    assert data["repository_id"] == repo_id
    discovered_files = data["files"]
    relative_paths = [f["relative_path"] for f in discovered_files]

    # Verify supported files are discovered
    assert "src/service.py" in relative_paths
    assert "src/index.ts" in relative_paths
    assert "src/Main.java" in relative_paths

    # Verify metadata fields
    service_meta = next(f for f in discovered_files if f["relative_path"] == "src/service.py")
    assert service_meta["extension"] == ".py"
    assert service_meta["size_bytes"] > 0
    assert service_meta["line_count"] > 10


def test_ignored_directories(client: TestClient, temp_sample_repo: Path):
    """Test 4: Ignored directories (.git, node_modules, .venv, __pycache__) are ignored."""
    reg_res = client.post(
        "/api/v1/repositories",
        json={"name": "ignored-test", "path": str(temp_sample_repo)},
    )
    repo_id = reg_res.json()["id"]

    files_res = client.get(f"/api/v1/repositories/{repo_id}/files")
    assert files_res.status_code == 200
    relative_paths = [f["relative_path"] for f in files_res.json()["files"]]

    # Ensure none of the files inside ignored directories are present
    for path in relative_paths:
        assert not path.startswith(".git")
        assert not path.startswith("node_modules")
        assert not path.startswith(".venv")
        assert "__pycache__" not in path

    # Ensure unsupported files like README.md are also omitted
    assert "README.md" not in relative_paths


def test_repository_analysis_summary(client: TestClient, temp_sample_repo: Path):
    """Test 11: Repository analysis summary returns accurate aggregate metrics."""
    reg_res = client.post(
        "/api/v1/repositories",
        json={"name": "analysis-test", "path": str(temp_sample_repo)},
    )
    repo_id = reg_res.json()["id"]

    analysis_res = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert analysis_res.status_code == 200
    summary = analysis_res.json()

    assert summary["repository_id"] == repo_id
    # We had 3 supported files: service.py, index.ts, Main.java
    assert summary["files_analyzed"] == 3
    # Exactly 1 Python file
    assert summary["python_files"] == 1
    # Classes in service.py: BaseCalculator and MathService (2 classes)
    assert summary["classes"] == 2
    # Functions in service.py: reset, add, compute_async, standalone_func (4 functions)
    assert summary["functions"] == 4
    # Imports in service.py: math, typing.Optional (2 imports)
    assert summary["imports"] == 2
    assert summary["errors"] == []


def test_repository_analysis_with_malformed_file(client: TestClient, temp_sample_repo: Path):
    """Verify that a malformed Python file does not crash the entire repository analysis."""
    bad_py = temp_sample_repo / "src" / "broken.py"
    bad_py.write_text("def syntax_error(:\n    pass\n", encoding="utf-8")

    reg_res = client.post(
        "/api/v1/repositories",
        json={"name": "malformed-analysis-test", "path": str(temp_sample_repo)},
    )
    repo_id = reg_res.json()["id"]

    analysis_res = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert analysis_res.status_code == 200
    summary = analysis_res.json()

    # Total python files is now 2 (service.py and broken.py)
    assert summary["python_files"] == 2
    # The valid service.py was still analyzed
    assert summary["classes"] == 2
    assert summary["functions"] == 4
    # The error was captured without crashing
    assert len(summary["errors"]) == 1
    assert "broken.py" in summary["errors"][0]


def test_repository_not_found_behavior(client: TestClient):
    """Test 12: Proper 404 response when repository ID does not exist."""
    non_existent_id = 999999

    get_res = client.get(f"/api/v1/repositories/{non_existent_id}")
    assert get_res.status_code == 404
    assert f"Repository with ID {non_existent_id} not found" in get_res.json()["detail"]

    files_res = client.get(f"/api/v1/repositories/{non_existent_id}/files")
    assert files_res.status_code == 404

    analyze_res = client.post(f"/api/v1/repositories/{non_existent_id}/analyze")
    assert analyze_res.status_code == 404

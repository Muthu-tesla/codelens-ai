import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.code_graph import CodeRelationship


@pytest.fixture
def call_graph_repo() -> Path:
    """Fixture providing a temporary Python codebase with various call patterns."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_calls_")
    root = Path(temp_dir)
    pkg = root / "pkg"
    pkg.mkdir()

    (pkg / "__init__.py").write_text("# init\n", encoding="utf-8")

    # 1. Same-module & recursive functions
    (pkg / "math_ops.py").write_text(
        'def add(a: int, b: int) -> int:\n'
        '    return a + b\n\n'
        'def compute(x: int) -> int:\n'
        '    return add(x, 1)\n\n'
        'def factorial(n: int) -> int:\n'
        '    if n <= 1:\n'
        '        return 1\n'
        '    return n * factorial(n - 1)\n',
        encoding="utf-8",
    )

    # 2. Same-class self calls & multiple calls
    (pkg / "order.py").write_text(
        'class OrderService:\n'
        '    def validate(self) -> bool:\n'
        '        return True\n\n'
        '    def log_status(self) -> None:\n'
        '        pass\n\n'
        '    def create(self) -> bool:\n'
        '        self.validate()\n'
        '        self.log_status()\n'
        '        # Duplicate self-call in same body\n'
        '        self.validate()\n'
        '        return True\n',
        encoding="utf-8",
    )

    # 3. Model with class constructor
    (pkg / "user.py").write_text(
        'class User:\n'
        '    def __init__(self, name: str):\n'
        '        self.name = name\n',
        encoding="utf-8",
    )

    # 4. Imported function, module-qualified call, constructor call, built-ins, and external calls
    (pkg / "service.py").write_text(
        'import os\n'
        'import requests\n'
        'from pkg import math_ops\n'
        'from pkg.user import User\n\n'
        'def build_user() -> User:\n'
        '    # Built-ins and external calls (should be ignored)\n'
        '    print("creating user")\n'
        '    os.getcwd()\n'
        '    len([1, 2, 3])\n'
        '    requests.get("https://example.com")\n'
        '    # Class constructor call\n'
        '    return User("alice")\n\n'
        'def calculate_score(val: int) -> int:\n'
        '    # Module-qualified call\n'
        '    return math_ops.compute(val)\n',
        encoding="utf-8",
    )

    return root


def test_same_module_function_call(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 1: Same-module function call resolution (compute -> add)."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-sm-call", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    res = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert res.status_code == 200

    calls = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .all()
    )

    call_pairs = {(r.source_symbol.qualified_name, r.target_symbol.qualified_name) for r in calls}
    assert ("pkg.math_ops.compute", "pkg.math_ops.add") in call_pairs


def test_same_class_self_method_call(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 2: Same-class self method call resolution (OrderService.create -> OrderService.validate)."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-self-call", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    calls = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .all()
    )

    call_pairs = {(r.source_symbol.qualified_name, r.target_symbol.qualified_name) for r in calls}
    assert ("pkg.order.OrderService.create", "pkg.order.OrderService.validate") in call_pairs
    assert ("pkg.order.OrderService.create", "pkg.order.OrderService.log_status") in call_pairs


def test_imported_repository_function_call(client: TestClient, db_session: Session):
    """Test 3: Directly imported repository function call (caller -> utils.helper)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "utils.py").write_text("def helper(): pass\n", encoding="utf-8")
        (root / "main.py").write_text("from utils import helper\ndef run(): helper()\n", encoding="utf-8")

        reg = client.post("/api/v1/repositories", json={"name": "repo-imp-call", "path": str(root)})
        repo_id = reg.json()["id"]
        client.post(f"/api/v1/repositories/{repo_id}/analyze")

        calls = (
            db_session.query(CodeRelationship)
            .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
            .all()
        )
        call_pairs = {(r.source_symbol.qualified_name, r.target_symbol.qualified_name) for r in calls}
        assert ("main.run", "utils.helper") in call_pairs


def test_module_qualified_repository_function_call(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 4: Module-qualified function call (service.calculate_score -> pkg.math_ops.compute)."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-mod-qual", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    calls = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .all()
    )

    call_pairs = {(r.source_symbol.qualified_name, r.target_symbol.qualified_name) for r in calls}
    assert ("pkg.service.calculate_score", "pkg.math_ops.compute") in call_pairs


def test_class_constructor_resolution(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 5: Class constructor instantiation call (service.build_user -> pkg.user.User)."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-ctor", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    calls = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .all()
    )

    call_pairs = {(r.source_symbol.qualified_name, r.target_symbol.qualified_name) for r in calls}
    assert ("pkg.service.build_user", "pkg.user.User") in call_pairs


def test_recursive_function(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 6: Recursive function call (factorial -> factorial)."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-recurse", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    calls = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .all()
    )

    factorial_calls = [
        r for r in calls
        if r.source_symbol.qualified_name == "pkg.math_ops.factorial"
        and r.target_symbol.qualified_name == "pkg.math_ops.factorial"
    ]
    # Self-recursion edge must exist exactly once
    assert len(factorial_calls) == 1


def test_external_function_ignored(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 7: External library calls (requests.get, os.getcwd) are ignored."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-ext-call", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    calls = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .all()
    )

    targets = {r.target_symbol.name for r in calls}
    assert "get" not in targets
    assert "getcwd" not in targets
    assert "requests" not in targets


def test_builtin_function_ignored(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 8: Built-in function calls (print, len) do NOT create call edges."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-builtins", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    calls = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .all()
    )

    targets = {r.target_symbol.name for r in calls}
    assert "print" not in targets
    assert "len" not in targets


def test_unresolved_function_ignored(client: TestClient, db_session: Session):
    """Test 9: Dynamic, unresolvable call expressions (callback()) are ignored."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "dyn.py").write_text("def run(callback):\n    callback()\n", encoding="utf-8")

        reg = client.post("/api/v1/repositories", json={"name": "repo-dyn", "path": str(root)})
        repo_id = reg.json()["id"]
        client.post(f"/api/v1/repositories/{repo_id}/analyze")

        calls = (
            db_session.query(CodeRelationship)
            .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
            .all()
        )
        assert len(calls) == 0


def test_multiple_calls_from_one_function(client: TestClient, db_session: Session):
    """Test 10: Multiple distinct function calls within a single caller body."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "pipeline.py").write_text(
            'def step_a(): pass\n'
            'def step_b(): pass\n'
            'def step_c(): pass\n'
            'def run_pipeline():\n'
            '    step_a()\n'
            '    step_b()\n'
            '    step_c()\n',
            encoding="utf-8",
        )

        reg = client.post("/api/v1/repositories", json={"name": "repo-multi-calls", "path": str(root)})
        repo_id = reg.json()["id"]
        client.post(f"/api/v1/repositories/{repo_id}/analyze")

        calls = (
            db_session.query(CodeRelationship)
            .filter(
                CodeRelationship.repository_id == repo_id,
                CodeRelationship.relationship_type == "calls",
            )
            .all()
        )

        targets = {r.target_symbol.name for r in calls if r.source_symbol.name == "run_pipeline"}
        assert targets == {"step_a", "step_b", "step_c"}


def test_duplicate_call_prevention(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 11: Duplicate invocations of self.validate() in same body create only 1 edge."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-dup-call", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    create_validate_calls = (
        db_session.query(CodeRelationship)
        .filter(
            CodeRelationship.repository_id == repo_id,
            CodeRelationship.relationship_type == "calls",
        )
        .all()
    )

    matching = [
        r for r in create_validate_calls
        if r.source_symbol.qualified_name == "pkg.order.OrderService.create"
        and r.target_symbol.qualified_name == "pkg.order.OrderService.validate"
    ]
    # Despite self.validate() appearing twice in OrderService.create, edge is recorded once
    assert len(matching) == 1


def test_call_relationship_api_filtering(client: TestClient, call_graph_repo: Path):
    """Test 12: GET /relationships?relationship_type=calls endpoint filters accurately."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-api-call", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.get(f"/api/v1/repositories/{repo_id}/relationships?relationship_type=calls")
    assert res.status_code == 200
    calls = res.json()
    assert len(calls) > 0
    assert all(r["relationship_type"] == "calls" for r in calls)

    # Validate source and target objects in JSON
    first = calls[0]
    assert "source_symbol" in first and "qualified_name" in first["source_symbol"]
    assert "target_symbol" in first and "qualified_name" in first["target_symbol"]


def test_reanalysis_idempotency_with_call_relationships(client: TestClient, call_graph_repo: Path, db_session: Session):
    """Test 13: Repeated analysis retains identical call relationships without duplication."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-idem-call", "path": str(call_graph_repo)})
    repo_id = reg.json()["id"]

    # Run 1
    res1 = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert res1.status_code == 200
    summary1 = res1.json()
    assert summary1["call_relationships"] > 0
    calls_count1 = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .count()
    )

    # Run 2
    res2 = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert res2.status_code == 200
    summary2 = res2.json()
    calls_count2 = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "calls")
        .count()
    )

    assert summary1["call_relationships"] == summary2["call_relationships"]
    assert calls_count1 == calls_count2
    assert summary1 == summary2

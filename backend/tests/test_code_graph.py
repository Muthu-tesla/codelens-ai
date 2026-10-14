import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.code_graph import CodeFile, CodeRelationship, CodeSymbol
from app.services.code_analyzer.qualified_names import (
    build_class_qualified_name,
    build_function_qualified_name,
    build_function_signature,
    build_method_qualified_name,
    file_path_to_module_name,
)


@pytest.fixture
def multi_module_repo() -> Path:
    """Create a temporary multi-module repository testing internal imports and inheritance."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_multimodule_")
    root = Path(temp_dir)

    models_dir = root / "app" / "models"
    services_dir = root / "app" / "services"
    models_dir.mkdir(parents=True)
    services_dir.mkdir(parents=True)

    # 1. Base model
    (models_dir / "user.py").write_text(
        'class User:\n'
        '    """User entity class."""\n'
        '    def __init__(self, username: str):\n'
        '        self.username = username\n',
        encoding="utf-8",
    )

    # 2. Service importing internal model and external library
    (services_dir / "user_service.py").write_text(
        'import os\n'
        'import sqlalchemy\n'
        'from app.models.user import User\n\n'
        'class UserService:\n'
        '    """User domain service."""\n'
        '    def get_user(self, user_id: int) -> User:\n'
        '        return User("test")\n\n'
        'def helper():\n'
        '    pass\n',
        encoding="utf-8",
    )

    return root


def test_codefile_persistence(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 1: CodeFile persistence into database for discovered files."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-files", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    code_files = db_session.query(CodeFile).filter(CodeFile.repository_id == repo_id).all()
    rel_paths = {cf.relative_path for cf in code_files}

    assert "src/service.py" in rel_paths
    assert "src/index.ts" in rel_paths
    assert "src/Main.java" in rel_paths

    py_file = next(cf for cf in code_files if cf.relative_path == "src/service.py")
    assert py_file.extension == ".py"
    assert py_file.size_bytes > 0
    assert py_file.line_count > 0


def test_python_module_symbol_persistence(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 2: Python module symbol persistence."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-mod", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    mod_sym = (
        db_session.query(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .filter(CodeFile.repository_id == repo_id, CodeSymbol.symbol_type == "module")
        .first()
    )

    assert mod_sym is not None
    assert mod_sym.qualified_name == "src.service"
    assert mod_sym.name == "service"
    assert mod_sym.line_start == 1


def test_class_persistence(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 3: Python class symbol persistence."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-cls", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    class_symbols = (
        db_session.query(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .filter(CodeFile.repository_id == repo_id, CodeSymbol.symbol_type == "class")
        .all()
    )

    class_names = {s.name: s for s in class_symbols}
    assert "BaseCalculator" in class_names
    assert "MathService" in class_names

    math_svc = class_names["MathService"]
    assert math_svc.qualified_name == "src.service.MathService"
    assert math_svc.docstring == "Service for math operations."
    assert "BaseCalculator" in math_svc.signature


def test_function_persistence(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 4: Top-level function symbol persistence."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-fn", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    fn_sym = (
        db_session.query(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .filter(CodeFile.repository_id == repo_id, CodeSymbol.symbol_type == "function")
        .first()
    )

    assert fn_sym is not None
    assert fn_sym.name == "standalone_func"
    assert fn_sym.qualified_name == "src.service.standalone_func"
    assert fn_sym.docstring == "A top-level helper function."
    assert "def standalone_func(x) -> str" in fn_sym.signature


def test_method_persistence(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 5: Class method symbol persistence."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-meth", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    methods = (
        db_session.query(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .filter(CodeFile.repository_id == repo_id, CodeSymbol.symbol_type == "method")
        .all()
    )

    method_map = {m.name: m for m in methods}
    assert "reset" in method_map
    assert "add" in method_map
    assert "compute_async" in method_map

    compute_m = method_map["compute_async"]
    assert compute_m.qualified_name == "src.service.MathService.compute_async"
    assert compute_m.signature.startswith("async def compute_async(")
    assert "-> int" in compute_m.signature
    assert compute_m.docstring == "Compute asynchronously."


def test_qualified_name_generation():
    """Test 6: Dedicated utility generates stable, robust qualified names and signatures."""
    assert file_path_to_module_name("app/services/order_service.py") == "app.services.order_service"
    assert file_path_to_module_name("app/core/__init__.py") == "app.core"
    assert file_path_to_module_name("service.py") == "service"

    cls_qname = build_class_qualified_name("app.services.order_service", "OrderService")
    assert cls_qname == "app.services.order_service.OrderService"

    meth_qname = build_method_qualified_name(cls_qname, "create_order")
    assert meth_qname == "app.services.order_service.OrderService.create_order"

    fn_qname = build_function_qualified_name("app.services.order_service", "validate_order")
    assert fn_qname == "app.services.order_service.validate_order"

    sig = build_function_signature("create_order", ["self", "user_id", "items"], "Order", False)
    assert sig == "def create_order(self, user_id, items) -> Order"

    sig_async = build_function_signature("fetch_data", ["url: str"], "dict", True)
    assert sig_async == "async def fetch_data(url: str) -> dict"


def test_contains_relationship(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 7: Contains relationship between module->function, module->class, class->method."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-contains", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    contains_rels = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "contains")
        .all()
    )

    edge_pairs = {
        (r.source_symbol.qualified_name, r.target_symbol.qualified_name)
        for r in contains_rels
    }

    # Module contains function
    assert ("src.service", "src.service.standalone_func") in edge_pairs
    # Module contains class
    assert ("src.service", "src.service.MathService") in edge_pairs
    assert ("src.service", "src.service.BaseCalculator") in edge_pairs
    # Class contains method
    assert ("src.service.MathService", "src.service.MathService.add") in edge_pairs
    assert ("src.service.BaseCalculator", "src.service.BaseCalculator.reset") in edge_pairs


def test_inheritance_relationship(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 8: Inheritance relationship between child class and parent class."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-inherits", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    inherits_rels = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "inherits")
        .all()
    )

    assert len(inherits_rels) == 1
    rel = inherits_rels[0]
    assert rel.source_symbol.qualified_name == "src.service.MathService"
    assert rel.target_symbol.qualified_name == "src.service.BaseCalculator"


def test_import_relationship_resolvable(client: TestClient, multi_module_repo: Path, db_session: Session):
    """Test 9: Import relationship resolved when target module/symbol belongs to repository."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-multi", "path": str(multi_module_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    import_rels = (
        db_session.query(CodeRelationship)
        .filter(CodeRelationship.repository_id == repo_id, CodeRelationship.relationship_type == "imports")
        .all()
    )

    assert len(import_rels) >= 1
    rel = import_rels[0]
    assert rel.source_symbol.qualified_name == "app.services.user_service"
    # Target is either module app.models.user or User class
    assert "app.models.user" in rel.target_symbol.qualified_name


def test_unresolved_external_import_handling(client: TestClient, multi_module_repo: Path, db_session: Session):
    """Test 10: External imports (os, sqlalchemy) do NOT create fake symbols or relationships."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-external", "path": str(multi_module_repo)})
    repo_id = reg.json()["id"]

    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    # Ensure no symbol named sqlalchemy or os was created
    fake_symbols = (
        db_session.query(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .filter(CodeFile.repository_id == repo_id, CodeSymbol.name.in_(["sqlalchemy", "os"]))
        .all()
    )
    assert len(fake_symbols) == 0


def test_symbol_search(client: TestClient, temp_sample_repo: Path):
    """Test 11: Symbol search query parameter on /symbols endpoint."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-search", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.get(f"/api/v1/repositories/{repo_id}/symbols?search=Math")
    assert res.status_code == 200
    symbols = res.json()
    assert len(symbols) >= 1
    assert any(s["name"] == "MathService" for s in symbols)
    assert all("math" in s["name"].lower() or "math" in s["qualified_name"].lower() for s in symbols)


def test_symbol_type_filtering(client: TestClient, temp_sample_repo: Path):
    """Test 12: Symbol type filtering on /symbols endpoint."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-filter", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    # Filter classes
    classes_res = client.get(f"/api/v1/repositories/{repo_id}/symbols?symbol_type=class")
    assert classes_res.status_code == 200
    classes = classes_res.json()
    assert len(classes) == 2
    assert all(c["symbol_type"] == "class" for c in classes)

    # Filter methods
    methods_res = client.get(f"/api/v1/repositories/{repo_id}/symbols?symbol_type=method")
    assert methods_res.status_code == 200
    methods = methods_res.json()
    assert len(methods) == 3
    assert all(m["symbol_type"] == "method" for m in methods)

    # Filter functions
    fn_res = client.get(f"/api/v1/repositories/{repo_id}/symbols?symbol_type=function")
    assert fn_res.status_code == 200
    fns = fn_res.json()
    assert len(fns) == 1
    assert fns[0]["symbol_type"] == "function"


def test_symbol_detail_endpoint(client: TestClient, temp_sample_repo: Path):
    """Test 13: Detailed symbol retrieval endpoint /symbols/{symbol_id}."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-detail", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    symbols_res = client.get(f"/api/v1/repositories/{repo_id}/symbols?search=MathService")
    math_sym = next(s for s in symbols_res.json() if s["name"] == "MathService")

    detail_res = client.get(f"/api/v1/repositories/{repo_id}/symbols/{math_sym['id']}")
    assert detail_res.status_code == 200
    detail = detail_res.json()

    assert detail["id"] == math_sym["id"]
    assert detail["name"] == "MathService"
    assert detail["qualified_name"] == "src.service.MathService"
    assert detail["relative_path"] == "src/service.py"
    assert len(detail["outgoing_relationships"]) > 0  # contains methods and inherits

    # 404 for invalid symbol
    notFound = client.get(f"/api/v1/repositories/{repo_id}/symbols/99999")
    assert notFound.status_code == 404


def test_relationship_endpoint(client: TestClient, temp_sample_repo: Path):
    """Test 14: Relationship edge listing and filtering endpoint."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-edges", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.get(f"/api/v1/repositories/{repo_id}/relationships")
    assert res.status_code == 200
    relationships = res.json()
    assert len(relationships) > 0

    first = relationships[0]
    assert "source_symbol" in first
    assert "target_symbol" in first
    assert "relationship_type" in first

    # Filter inherits
    inherits_res = client.get(f"/api/v1/repositories/{repo_id}/relationships?relationship_type=inherits")
    assert inherits_res.status_code == 200
    inherits = inherits_res.json()
    assert len(inherits) == 1
    assert inherits[0]["relationship_type"] == "inherits"


def test_repeated_analysis_idempotency(client: TestClient, temp_sample_repo: Path, db_session: Session):
    """Test 15: Repeated analysis does NOT duplicate CodeFiles, CodeSymbols, or CodeRelationships."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-idempotency", "path": str(temp_sample_repo)})
    repo_id = reg.json()["id"]

    # First analysis
    run1 = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert run1.status_code == 200
    summary1 = run1.json()

    files_count1 = db_session.query(CodeFile).filter(CodeFile.repository_id == repo_id).count()
    symbols_count1 = (
        db_session.query(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .filter(CodeFile.repository_id == repo_id)
        .count()
    )
    rels_count1 = db_session.query(CodeRelationship).filter(CodeRelationship.repository_id == repo_id).count()

    # Second analysis
    run2 = client.post(f"/api/v1/repositories/{repo_id}/analyze")
    assert run2.status_code == 200
    summary2 = run2.json()

    files_count2 = db_session.query(CodeFile).filter(CodeFile.repository_id == repo_id).count()
    symbols_count2 = (
        db_session.query(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .filter(CodeFile.repository_id == repo_id)
        .count()
    )
    rels_count2 = db_session.query(CodeRelationship).filter(CodeRelationship.repository_id == repo_id).count()

    # Exactly identical counts
    assert files_count1 == files_count2
    assert symbols_count1 == symbols_count2
    assert rels_count1 == rels_count2
    assert summary1 == summary2

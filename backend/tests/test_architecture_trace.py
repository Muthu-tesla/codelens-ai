import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.architecture.trace_service import trace_service
from app.schemas.architecture import ArchitectureTraceRequest


@pytest.fixture
def cycle_and_diamond_repo() -> Path:
    """Fixture with cyclic calls (A -> B -> C -> A) and diamond calls (root -> left, root -> right, left -> bottom, right -> bottom)."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_trace_repo_")
    root = Path(temp_dir)
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("# init\n", encoding="utf-8")

    # Cycle: a -> b -> c -> a
    (pkg / "cycle.py").write_text(
        'def step_a() -> None:\n'
        '    step_b()\n\n'
        'def step_b() -> None:\n'
        '    step_c()\n\n'
        'def step_c() -> None:\n'
        '    step_a()\n',
        encoding="utf-8",
    )

    # Diamond: start -> branch_one, start -> branch_two; both branch_one and branch_two -> sink
    (pkg / "diamond.py").write_text(
        'def sink() -> None:\n'
        '    pass\n\n'
        'def branch_one() -> None:\n'
        '    sink()\n\n'
        'def branch_two() -> None:\n'
        '    sink()\n\n'
        'def diamond_root() -> None:\n'
        '    branch_one()\n'
        '    branch_two()\n',
        encoding="utf-8",
    )

    return root


@pytest.fixture
def order_fixture_repo() -> Path:
    """Path to the deterministic rag_fixture_a repository."""
    return Path(__file__).resolve().parent / "fixtures" / "rag_fixture_a"


@pytest.fixture
def order_fixture_b_repo() -> Path:
    """Path to the deterministic rag_fixture_b repository."""
    return Path(__file__).resolve().parent / "fixtures" / "rag_fixture_b"


def test_trace_a_to_b(client: TestClient, cycle_and_diamond_repo: Path):
    """Test 1: Simple 1-hop call trace (branch_one -> sink) including source_line."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-a-to-b", "path": str(cycle_and_diamond_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "pkg.diamond.branch_one"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["start_symbol"] == "pkg.diamond.branch_one"
    assert len(data["nodes"]) == 2
    assert [n["qualified_name"] for n in data["nodes"]] == ["pkg.diamond.branch_one", "pkg.diamond.sink"]
    assert len(data["edges"]) == 1
    assert data["edges"][0] == {
        "from": "pkg.diamond.branch_one",
        "to": "pkg.diamond.sink",
        "relationship": "calls",
        "source_line": 5,
    }


def test_trace_a_to_b_to_c(client: TestClient, cycle_and_diamond_repo: Path):
    """Test 2: Transitive 2-hop linear call trace (diamond_root -> branch_one -> sink)."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-a-b-c", "path": str(cycle_and_diamond_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "pkg.diamond.diamond_root"},
    )
    assert res.status_code == 200
    data = res.json()

    qnames = [n["qualified_name"] for n in data["nodes"]]
    assert "pkg.diamond.diamond_root" in qnames
    assert "pkg.diamond.branch_one" in qnames
    assert "pkg.diamond.branch_two" in qnames
    assert "pkg.diamond.sink" in qnames


def test_trace_current_order_flow(client: TestClient, order_fixture_repo: Path):
    """Test 3: Trace the complete order processing execution flow in rag_fixture_a respecting source call-site order."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-order-flow", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    )
    assert res.status_code == 200
    data = res.json()

    node_qnames = [n["qualified_name"] for n in data["nodes"]]
    assert data["start_symbol"] == "orders.service.OrderService.create_order"

    # Exact source call-site execution order:
    # OrderService.create_order
    #   -> InventoryService.check_stock
    #   -> PaymentService.process_payment
    #     -> StripeGateway.charge_card
    #   -> OrderRepository.save_order
    assert node_qnames == [
        "orders.service.OrderService.create_order",
        "inventory.service.InventoryService.check_stock",
        "payments.service.PaymentService.process_payment",
        "payments.gateway.StripeGateway.charge_card",
        "database.repository.OrderRepository.save_order",
    ]

    # Verify edge sequence and source_line numbers
    assert data["edges"] == [
        {
            "from": "orders.service.OrderService.create_order",
            "to": "inventory.service.InventoryService.check_stock",
            "relationship": "calls",
            "source_line": 30,
        },
        {
            "from": "orders.service.OrderService.create_order",
            "to": "payments.service.PaymentService.process_payment",
            "relationship": "calls",
            "source_line": 35,
        },
        {
            "from": "payments.service.PaymentService.process_payment",
            "to": "payments.gateway.StripeGateway.charge_card",
            "relationship": "calls",
            "source_line": 14,
        },
        {
            "from": "orders.service.OrderService.create_order",
            "to": "database.repository.OrderRepository.save_order",
            "relationship": "calls",
            "source_line": 45,
        },
    ]

    # Check node metadata attributes
    first_node = data["nodes"][0]
    assert first_node["step"] == 1
    assert first_node["file"] == "orders/service.py"
    assert first_node["symbol_type"] == "method"
    assert first_node["line_start"] is not None
    assert first_node["line_end"] is not None


def test_deterministic_node_ordering(client: TestClient, order_fixture_repo: Path):
    """Test 4: Node ordering is deterministic across repeated requests."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-node-order", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res1 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    ).json()

    res2 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    ).json()

    assert [n["qualified_name"] for n in res1["nodes"]] == [n["qualified_name"] for n in res2["nodes"]]
    assert [n["step"] for n in res1["nodes"]] == [n["step"] for n in res2["nodes"]]


def test_deterministic_edge_ordering(client: TestClient, order_fixture_repo: Path):
    """Test 5: Edge ordering is deterministic across repeated requests."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-edge-order", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res1 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    ).json()

    res2 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    ).json()

    assert [(e["from"], e["to"]) for e in res1["edges"]] == [(e["from"], e["to"]) for e in res2["edges"]]


def test_max_depth_constraint(db_session: Session, order_fixture_repo: Path, client: TestClient):
    """Test 6: Traversal depth limit strictly bounds call chain expansion."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-depth", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    # Depth 1: Only direct callees of create_order (OrderRepository.save_order, InventoryService.check_stock, PaymentService.process_payment)
    # StripeGateway.charge_card is at depth 2 from create_order and must NOT be visited.
    res_depth_1 = trace_service.trace_architecture(
        db=db_session,
        repository_id=repo_id,
        request=ArchitectureTraceRequest(start_symbol="orders.service.OrderService.create_order"),
        max_depth=1,
    )
    qnames_1 = [n.qualified_name for n in res_depth_1.nodes]
    assert "payments.gateway.StripeGateway.charge_card" not in qnames_1
    assert "payments.service.PaymentService.process_payment" in qnames_1

    # Depth 2: StripeGateway.charge_card IS reached
    res_depth_2 = trace_service.trace_architecture(
        db=db_session,
        repository_id=repo_id,
        request=ArchitectureTraceRequest(start_symbol="orders.service.OrderService.create_order"),
        max_depth=2,
    )
    qnames_2 = [n.qualified_name for n in res_depth_2.nodes]
    assert "payments.gateway.StripeGateway.charge_card" in qnames_2


def test_max_node_count_constraint(db_session: Session, order_fixture_repo: Path, client: TestClient):
    """Test 7: Traversal node count limit strictly caps discovered nodes."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-max-nodes", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res_capped = trace_service.trace_architecture(
        db=db_session,
        repository_id=repo_id,
        request=ArchitectureTraceRequest(start_symbol="orders.service.OrderService.create_order"),
        max_nodes=3,
    )
    assert len(res_capped.nodes) == 3


def test_cycle_protection(client: TestClient, cycle_and_diamond_repo: Path):
    """Test 8: Cyclic calls (A -> B -> C -> A) terminate safely without infinite recursion."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-cycle", "path": str(cycle_and_diamond_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "pkg.cycle.step_a"},
    )
    assert res.status_code == 200
    data = res.json()

    # Must contain exactly the 3 distinct nodes in the cycle
    assert len(data["nodes"]) == 3
    qnames = [n["qualified_name"] for n in data["nodes"]]
    assert qnames == ["pkg.cycle.step_a", "pkg.cycle.step_b", "pkg.cycle.step_c"]

    # Edges must include the cycle-closing edge C -> A
    edge_pairs = [(e["from"], e["to"]) for e in data["edges"]]
    assert ("pkg.cycle.step_a", "pkg.cycle.step_b") in edge_pairs
    assert ("pkg.cycle.step_b", "pkg.cycle.step_c") in edge_pairs
    assert ("pkg.cycle.step_c", "pkg.cycle.step_a") in edge_pairs


def test_duplicate_prevention(client: TestClient, cycle_and_diamond_repo: Path):
    """Test 9: Reconverging / diamond paths visit shared targets only once in nodes list."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-diamond", "path": str(cycle_and_diamond_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "pkg.diamond.diamond_root"},
    )
    assert res.status_code == 200
    data = res.json()

    # sink is called by both branch_one and branch_two, but must appear only ONCE in nodes
    sink_nodes = [n for n in data["nodes"] if n["qualified_name"] == "pkg.diamond.sink"]
    assert len(sink_nodes) == 1

    # But both edges must be present
    edge_pairs = [(e["from"], e["to"]) for e in data["edges"]]
    assert ("pkg.diamond.branch_one", "pkg.diamond.sink") in edge_pairs
    assert ("pkg.diamond.branch_two", "pkg.diamond.sink") in edge_pairs


def test_nonexistent_symbol(client: TestClient, order_fixture_repo: Path):
    """Test 10: Nonexistent start symbol returns 404 without fuzzy/semantic fallback."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-404-sym", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.nonexistent_method"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_symbol_with_no_outgoing_calls(client: TestClient, order_fixture_repo: Path):
    """Test 11: Symbol with no outgoing calls returns 1 node, 0 edges, and clean summary."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-leaf", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "inventory.service.InventoryService.check_stock"},
    )
    assert res.status_code == 200
    data = res.json()

    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["qualified_name"] == "inventory.service.InventoryService.check_stock"
    assert len(data["edges"]) == 0
    assert "no outgoing calls" in data["summary"].lower()


def test_repository_isolation(client: TestClient, order_fixture_repo: Path, order_fixture_b_repo: Path):
    """Test 12: Symbol from another repository cannot be traced or traversed."""
    reg_a = client.post("/api/v1/repositories", json={"name": "repo-iso-a", "path": str(order_fixture_repo)})
    repo_a_id = reg_a.json()["id"]
    client.post(f"/api/v1/repositories/{repo_a_id}/analyze")

    reg_b = client.post("/api/v1/repositories", json={"name": "repo-iso-b", "path": str(order_fixture_b_repo)})
    repo_b_id = reg_b.json()["id"]
    client.post(f"/api/v1/repositories/{repo_b_id}/analyze")

    # Attempt to trace a PayPal symbol (exists only in Repo B) against Repo A
    res = client.post(
        f"/api/v1/repositories/{repo_a_id}/architecture/trace",
        json={"start_symbol": "payments.gateway.PayPalGateway.process_transaction"},
    )
    assert res.status_code == 404


def test_repeated_request_produces_identical_output(client: TestClient, order_fixture_repo: Path):
    """Test 13: Repeated requests produce completely identical JSON output."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-determinism", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res1 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    )
    res2 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    )

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json() == res2.json()


def test_call_relationship_stores_source_line(client: TestClient, order_fixture_repo: Path):
    """Test 14: CALL relationships persist source_line metadata."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-call-meta", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "orders.service.OrderService.create_order"},
    )
    assert res.status_code == 200
    data = res.json()

    # Verify all trace edges contain positive integer source_line
    assert len(data["edges"]) == 4
    for edge in data["edges"]:
        assert isinstance(edge["source_line"], int)
        assert edge["source_line"] > 0

    # Also check through the relationships API endpoint
    rel_res = client.get(f"/api/v1/repositories/{repo_id}/relationships?relationship_type=calls")
    assert rel_res.status_code == 200
    rels = rel_res.json()
    assert len(rels) >= 4
    calls_map = {(r["source_symbol"]["name"], r["target_symbol"]["name"]): r.get("source_line") for r in rels}
    assert calls_map[("create_order", "check_stock")] == 30
    assert calls_map[("create_order", "process_payment")] == 35
    assert calls_map[("process_payment", "charge_card")] == 14
    assert calls_map[("create_order", "save_order")] == 45


def test_earlier_source_call_before_later_source_call(client: TestClient):
    """Test 15: Earlier source call appears before later source call regardless of alphabetical naming."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_order_test_")
    root = Path(temp_dir)
    pkg = root / "ordering_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    # Name target 1 'zebra' and target 2 'alpha' to ensure alphabetical sorting does NOT invert source order
    (pkg / "service.py").write_text(
        "def zebra() -> None:\n"
        "    pass\n\n"
        "def alpha() -> None:\n"
        "    pass\n\n"
        "def run_workflow() -> None:\n"
        "    zebra()\n"
        "    alpha()\n",
        encoding="utf-8",
    )

    reg = client.post("/api/v1/repositories", json={"name": "repo-early-late", "path": str(root)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "ordering_pkg.service.run_workflow"},
    )
    assert res.status_code == 200
    data = res.json()

    # zebra is on line 8, alpha is on line 9
    node_names = [n["name"] for n in data["nodes"]]
    assert node_names == ["run_workflow", "zebra", "alpha"]

    edge_lines = [(e["to"], e["source_line"]) for e in data["edges"]]
    assert edge_lines == [
        ("ordering_pkg.service.zebra", 8),
        ("ordering_pkg.service.alpha", 9),
    ]


def test_same_source_line_uses_deterministic_qualified_name_ordering(client: TestClient):
    """Test 16: When calls share the exact same source line, secondary sort by qualified name is used."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_same_line_")
    root = Path(temp_dir)
    pkg = root / "sameline_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    # Both zebra and alpha are invoked on the exact same line (line 8)
    (pkg / "service.py").write_text(
        "def zebra() -> None:\n"
        "    pass\n\n"
        "def alpha() -> None:\n"
        "    pass\n\n"
        "def caller() -> None:\n"
        "    zebra(); alpha()\n",
        encoding="utf-8",
    )

    reg = client.post("/api/v1/repositories", json={"name": "repo-same-line", "path": str(root)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "sameline_pkg.service.caller"},
    )
    assert res.status_code == 200
    data = res.json()

    # Since source_line is equal (8), secondary ordering (qualified_name asc) places alpha before zebra
    node_names = [n["name"] for n in data["nodes"]]
    assert node_names == ["caller", "alpha", "zebra"]

    assert data["edges"][0]["to"] == "sameline_pkg.service.alpha"
    assert data["edges"][0]["source_line"] == 8
    assert data["edges"][1]["to"] == "sameline_pkg.service.zebra"
    assert data["edges"][1]["source_line"] == 8


def test_reanalysis_does_not_create_duplicate_relationships(client: TestClient, order_fixture_repo: Path):
    """Test 17: Re-analysis is idempotent and does not create duplicate CALLS relationships."""
    reg = client.post("/api/v1/repositories", json={"name": "repo-idempotency", "path": str(order_fixture_repo)})
    repo_id = reg.json()["id"]

    # First analysis
    client.post(f"/api/v1/repositories/{repo_id}/analyze")
    rels1 = client.get(f"/api/v1/repositories/{repo_id}/relationships?relationship_type=calls").json()

    # Second analysis
    client.post(f"/api/v1/repositories/{repo_id}/analyze")
    rels2 = client.get(f"/api/v1/repositories/{repo_id}/relationships?relationship_type=calls").json()

    assert len(rels1) == len(rels2)
    pairs1 = sorted([(r["source_symbol"]["qualified_name"], r["target_symbol"]["qualified_name"]) for r in rels1])
    pairs2 = sorted([(r["source_symbol"]["qualified_name"], r["target_symbol"]["qualified_name"]) for r in rels2])
    assert pairs1 == pairs2


def test_moving_call_to_another_source_line_updates_source_line(client: TestClient):
    """Test 18: Moving a call to another line updates the source_line metadata upon re-analysis."""
    temp_dir = tempfile.mkdtemp(prefix="codelens_move_line_")
    root = Path(temp_dir)
    pkg = root / "move_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    code_file = pkg / "worker.py"
    # Call on line 5
    code_file.write_text(
        "def work() -> None:\n"
        "    pass\n\n"
        "def dispatch() -> None:\n"
        "    work()\n",
        encoding="utf-8",
    )

    reg = client.post("/api/v1/repositories", json={"name": "repo-move-line", "path": str(root)})
    repo_id = reg.json()["id"]
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    res1 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "move_pkg.worker.dispatch"},
    )
    assert res1.status_code == 200
    assert res1.json()["edges"][0]["source_line"] == 5

    rels1 = client.get(f"/api/v1/repositories/{repo_id}/relationships?relationship_type=calls").json()
    assert len(rels1) == 1
    assert rels1[0]["source_line"] == 5

    # Now move work() down by inserting 5 blank comment lines (moving from line 5 to line 10)
    code_file.write_text(
        "def work() -> None:\n"
        "    pass\n\n"
        "def dispatch() -> None:\n"
        "    # comment 1\n"
        "    # comment 2\n"
        "    # comment 3\n"
        "    # comment 4\n"
        "    # comment 5\n"
        "    work()\n",
        encoding="utf-8",
    )

    # Re-analyze repository
    client.post(f"/api/v1/repositories/{repo_id}/analyze")

    # Relationship count must not duplicate
    rels2 = client.get(f"/api/v1/repositories/{repo_id}/relationships?relationship_type=calls").json()
    assert len(rels2) == 1
    assert rels2[0]["source_line"] == 10

    # Architecture trace must reflect updated line number 10
    res2 = client.post(
        f"/api/v1/repositories/{repo_id}/architecture/trace",
        json={"start_symbol": "move_pkg.worker.dispatch"},
    )
    assert res2.status_code == 200
    assert res2.json()["edges"][0]["source_line"] == 10

"""
Unit and referential integrity tests for Phase 4B.3 Precomputed TinyDB Showcase Data.
Validates all 6 exported showcase JSON datasets against required schemas, constraints,
referential integrity, security, and payload budgets.
"""
import json
import re
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SHOWCASE_DIR = WORKSPACE_ROOT / "frontend" / "src" / "data" / "showcase"
TINYDB_REPO_PATH = WORKSPACE_ROOT / "evaluation_repos" / "tinydb"


def test_showcase_directory_and_all_six_files_exist() -> None:
    """Verify that frontend/src/data/showcase exists and contains all 6 required datasets."""
    assert SHOWCASE_DIR.exists(), f"Showcase directory does not exist: {SHOWCASE_DIR}"

    expected_files = [
        "repository.json",
        "files.json",
        "symbols.json",
        "symbol_details.json",
        "relationships.json",
        "traces.json",
    ]
    for filename in expected_files:
        filepath = SHOWCASE_DIR / filename
        assert filepath.exists(), f"Required dataset missing: {filepath}"
        assert filepath.stat().st_size > 0, f"Dataset is empty: {filepath}"


def test_repository_json_metadata_and_statistics() -> None:
    """Verify repository.json schema, benchmark commit, MIT license, and verified statistics."""
    repo_file = SHOWCASE_DIR / "repository.json"
    with open(repo_file, "r", encoding="utf-8") as f:
        repo = json.load(f)

    assert repo["id"] == 1
    assert repo["name"] == "tinydb"
    assert repo["path"] == "evaluation_repos/tinydb"
    assert repo["version"] == "v4.8.2"
    assert repo["commit"] == "6d7c4fc3e04d398b1282876514660a33a7897b41"
    assert repo["license"] == "MIT License"
    assert "MIT License" in repo["attribution"]
    assert repo["is_indexed"] is True
    assert repo["symbol_count"] == 314
    assert repo["file_count"] == 21

    # Verified statistics
    stats = repo["analysis_summary"]
    assert stats["files_analyzed"] == 21
    assert stats["python_files"] == 21
    assert stats["classes"] == 15
    assert stats["functions"] == 286
    assert stats["methods"] == 113
    assert stats["imports"] == 141
    assert stats["call_relationships"] == 226
    assert stats["relationships"] == 559
    assert stats["chunks_created"] == 314
    assert stats["embeddings_generated"] == 314
    assert stats["errors"] == []

    # Benchmark metrics
    metrics = repo["benchmark_metrics"]
    assert metrics["queries_evaluated"] == 13
    assert metrics["positive_queries"] == 10
    assert metrics["negative_queries"] == 3
    assert metrics["start_symbol_accuracy"] == 1.0
    assert metrics["edge_precision"] == 1.0
    assert metrics["edge_recall"] == 1.0
    assert metrics["edge_f1"] == 1.0
    assert metrics["exact_trace_match"] == 1.0
    assert metrics["negative_query_accuracy"] == 1.0


def test_files_json_matches_disk_python_files() -> None:
    """Verify files.json contains exactly the 21 Python files with relative paths."""
    files_file = SHOWCASE_DIR / "files.json"
    with open(files_file, "r", encoding="utf-8") as f:
        files = json.load(f)

    assert isinstance(files, list)
    assert len(files) == 21

    for f in files:
        assert isinstance(f["id"], int)
        assert f["repository_id"] == 1
        assert f["extension"] == ".py"
        assert f["size_bytes"] >= 0
        assert f["line_count"] >= 0
        assert not Path(f["relative_path"]).is_absolute()
        assert not f["relative_path"].startswith("\\")
        assert not f["relative_path"].startswith("/")

        # Verify file exists in actual TinyDB repo on disk
        disk_file = TINYDB_REPO_PATH / f["relative_path"]
        assert disk_file.exists(), f"File in files.json does not exist on disk: {disk_file}"


def test_symbols_json_schema_and_counts() -> None:
    """Verify symbols.json contains all 314 indexed symbols with actual identifiers."""
    with open(SHOWCASE_DIR / "symbols.json", "r", encoding="utf-8") as f:
        symbols = json.load(f)

    assert isinstance(symbols, list)
    assert len(symbols) == 314

    with open(SHOWCASE_DIR / "files.json", "r", encoding="utf-8") as f:
        files = json.load(f)
    valid_file_ids = {f["id"] for f in files}

    for s in symbols:
        assert isinstance(s["id"], int)
        assert s["file_id"] in valid_file_ids
        assert isinstance(s["name"], str) and len(s["name"]) > 0
        assert isinstance(s["qualified_name"], str) and len(s["qualified_name"]) > 0
        assert s["symbol_type"] in ("module", "class", "function", "method")
        assert s["line_start"] >= 1
        assert s["line_end"] >= s["line_start"]


def test_symbol_details_json_referential_integrity() -> None:
    """Verify symbol_details.json includes docstrings, excerpts, and incoming/outgoing edges."""
    with open(SHOWCASE_DIR / "symbol_details.json", "r", encoding="utf-8") as f:
        details = json.load(f)

    with open(SHOWCASE_DIR / "symbols.json", "r", encoding="utf-8") as f:
        symbols = json.load(f)
    valid_symbol_ids = {s["id"] for s in symbols}

    assert len(details) == 314
    for sid_str, detail in details.items():
        sid = int(sid_str)
        assert sid in valid_symbol_ids
        assert detail["id"] == sid
        assert "outgoing_relationships" in detail
        assert "incoming_relationships" in detail
        assert "source_excerpt" in detail

    # Verify key symbol: Table.insert
    insert_sym = next(s for s in symbols if s["qualified_name"] == "tinydb.table.Table.insert")
    insert_detail = details[str(insert_sym["id"])]
    assert insert_detail["name"] == "insert"
    assert "Insert a new document into the table." in (insert_detail["docstring"] or "")
    assert "def insert" in (insert_detail["source_excerpt"] or "")
    assert len(insert_detail["outgoing_relationships"]) >= 2


def test_relationships_json_ast_call_edges() -> None:
    """Verify relationships.json has exactly 226 AST-extracted call edges with source lines."""
    with open(SHOWCASE_DIR / "relationships.json", "r", encoding="utf-8") as f:
        rels = json.load(f)

    with open(SHOWCASE_DIR / "symbols.json", "r", encoding="utf-8") as f:
        symbols = json.load(f)
    valid_symbol_ids = {s["id"] for s in symbols}

    assert isinstance(rels, list)
    assert len(rels) == 226

    for r in rels:
        assert isinstance(r["id"], int)
        assert r["repository_id"] == 1
        assert r["relationship_type"] == "calls"
        assert r["source_line"] is not None and r["source_line"] > 0
        assert r["source_symbol"]["id"] in valid_symbol_ids
        assert r["target_symbol"]["id"] in valid_symbol_ids


def test_traces_json_provenance_and_ast_marking() -> None:
    """Verify traces.json is marked as static AST-derived traces, not runtime traces."""
    with open(SHOWCASE_DIR / "traces.json", "r", encoding="utf-8") as f:
        traces_payload = json.load(f)

    prov = traces_payload["provenance"]
    assert prov["trace_type"] == "static_ast_derived"
    assert prov["is_runtime_execution"] is False
    assert "static AST-derived" in prov["description"]
    assert prov["total_benchmark_queries"] == 13
    assert prov["positive_benchmark_queries"] == 10
    assert prov["negative_benchmark_queries"] == 3

    # Benchmark queries
    b_queries = traces_payload["benchmark_queries"]
    assert len(b_queries) == 13

    # Check positive queries have valid traces and evidence
    positive = [q for q in b_queries if not q["is_negative"]]
    assert len(positive) == 10
    for q in positive:
        assert q["resolved_start_symbol"] is not None
        assert q["trace"] is not None
        assert len(q["trace"]["nodes"]) >= 1
        assert isinstance(q["evidence"], list)

    # Check negative queries gracefully refuse
    negative = [q for q in b_queries if q["is_negative"]]
    assert len(negative) == 3
    for q in negative:
        assert q["resolved_start_symbol"] is None
        assert q["trace"] is None
        assert "couldn't determine this confidently" in q["answer"]
        assert q["evidence"] == []

    # Symbol traces precomputed
    sym_traces = traces_payload["symbol_traces"]
    assert len(sym_traces) >= 100
    assert "tinydb.table.Table.insert" in sym_traces


def test_data_hygiene_zero_machine_paths() -> None:
    """Verify all repository paths are relative and no machine-specific paths exist."""
    machine_path_patterns = [
        re.compile(r"^[a-zA-Z]:\\", re.IGNORECASE),
        re.compile(r"^/home/", re.IGNORECASE),
        re.compile(r"^/Users/", re.IGNORECASE),
        re.compile(r"muthu", re.IGNORECASE),
        re.compile(r"ai_resuem_project", re.IGNORECASE),
    ]

    for json_file in SHOWCASE_DIR.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            content_str = f.read()
        for pat in machine_path_patterns:
            match = pat.search(content_str)
            assert match is None, f"Found machine-specific path in {json_file.name}: {match.group(0)}"


def test_data_security_no_credentials_or_secrets() -> None:
    """Verify no database credentials, environment variables, or secret keys exist in datasets."""
    secret_patterns = [
        re.compile(r"postgres://", re.IGNORECASE),
        re.compile(r"postgresql://", re.IGNORECASE),
        re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    ]

    for json_file in SHOWCASE_DIR.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            content_str = f.read()
        for pat in secret_patterns:
            assert not pat.search(content_str), f"Found potential secret in {json_file.name}"


def test_payload_size_budget() -> None:
    """Verify total showcase payload is well within the 2MB budget."""
    total_bytes = sum(f.stat().st_size for f in SHOWCASE_DIR.glob("*.json"))
    assert total_bytes < 2 * 1024 * 1024, f"Payload size {total_bytes} bytes exceeds 2MB budget"
    assert total_bytes > 1_000_000, f"Payload unexpectedly small: {total_bytes} bytes"

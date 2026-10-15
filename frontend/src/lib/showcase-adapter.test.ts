import { test, describe } from "node:test";
import assert from "node:assert/strict";

import {
  checkShowcaseHealth,
  getInitialShowcaseFiles,
  getInitialShowcaseRelationships,
  getInitialShowcaseRepoStatus,
  getInitialShowcaseSelectedRepoId,
  getInitialShowcaseSymbols,
  getShowcaseBenchmarkQueries,
  getShowcaseExplain,
  getShowcaseFiles,
  getShowcaseMetadata,
  getShowcaseRelationships,
  getShowcaseRepositories,
  getShowcaseRepository,
  getShowcaseSymbolDetail,
  getShowcaseSymbols,
  getShowcaseTrace,
  isShowcaseMode,
  validateShowcaseData,
} from "./showcase-adapter.ts";

describe("Static Showcase Adapter (Phase 4B.4)", () => {
  test("validateShowcaseData verifies presence and schema of all 6 showcase datasets", () => {
    const result = validateShowcaseData();
    assert.strictEqual(result.isValid, true);
    assert.strictEqual(result.error, null);
  });

  test("isShowcaseMode evaluates NEXT_PUBLIC_SHOWCASE_MODE correctly", () => {
    const original = process.env.NEXT_PUBLIC_SHOWCASE_MODE;
    try {
      delete process.env.NEXT_PUBLIC_SHOWCASE_MODE;
      assert.strictEqual(isShowcaseMode(), false);

      process.env.NEXT_PUBLIC_SHOWCASE_MODE = "false";
      assert.strictEqual(isShowcaseMode(), false);

      process.env.NEXT_PUBLIC_SHOWCASE_MODE = "0";
      assert.strictEqual(isShowcaseMode(), false);

      process.env.NEXT_PUBLIC_SHOWCASE_MODE = "true";
      assert.strictEqual(isShowcaseMode(), true);

      process.env.NEXT_PUBLIC_SHOWCASE_MODE = "1";
      assert.strictEqual(isShowcaseMode(), true);
    } finally {
      process.env.NEXT_PUBLIC_SHOWCASE_MODE = original;
    }
  });

  test("checkShowcaseHealth returns showcase status without network requests", async () => {
    const health = await checkShowcaseHealth();
    assert.strictEqual(health.status, "showcase");
    assert.ok(health.service.includes("TinyDB v4.8.2"));
  });

  test("getShowcaseRepository returns TinyDB with MIT license and statistics", async () => {
    const repo = await getShowcaseRepository();
    assert.strictEqual(repo.id, 1);
    assert.strictEqual(repo.name, "tinydb");
    assert.strictEqual(repo.path, "evaluation_repos/tinydb");

    const metadata = getShowcaseMetadata();
    assert.strictEqual(metadata.license, "MIT License");
    assert.strictEqual(metadata.commit, "6d7c4fc3e04d398b1282876514660a33a7897b41");
    assert.ok(metadata.attribution.includes("Markus Siemens"));
    assert.strictEqual(metadata.analysis_summary.files_analyzed, 21);
    assert.strictEqual(metadata.analysis_summary.classes, 15);
    assert.strictEqual(metadata.analysis_summary.functions, 286);
    assert.strictEqual(metadata.analysis_summary.call_relationships, 226);
    assert.strictEqual(metadata.benchmark_metrics.exact_trace_match, 1.0);
  });

  test("getShowcaseRepositories returns singleton repository array", async () => {
    const repos = await getShowcaseRepositories();
    assert.strictEqual(repos.length, 1);
    assert.strictEqual(repos[0].name, "tinydb");
  });

  test("getShowcaseFiles returns all 21 Python files with relative paths", async () => {
    const filesRes = await getShowcaseFiles();
    assert.strictEqual(filesRes.total_files, 21);
    assert.strictEqual(filesRes.files.length, 21);

    for (const file of filesRes.files) {
      assert.strictEqual(file.extension, ".py");
      assert.ok(!file.relative_path.startsWith("/"));
      assert.ok(!file.relative_path.startsWith("\\"));
      assert.ok(!file.relative_path.includes("C:"));
    }
  });

  test("getShowcaseSymbols supports symbolType and search filtering", async () => {
    const allSyms = await getShowcaseSymbols();
    assert.strictEqual(allSyms.length, 314);

    const classes = await getShowcaseSymbols(1, { symbolType: "class" });
    assert.strictEqual(classes.length, 15);
    assert.ok(classes.every((c) => c.symbol_type === "class"));

    const searchMatches = await getShowcaseSymbols(1, { search: "insert" });
    assert.ok(searchMatches.length > 0);
    assert.ok(searchMatches.some((s) => s.qualified_name === "tinydb.table.Table.insert"));
  });

  test("getShowcaseSymbolDetail returns docstrings, excerpts, and relationships", async () => {
    const allSyms = await getShowcaseSymbols();
    const insertSym = allSyms.find((s) => s.qualified_name === "tinydb.table.Table.insert")!;
    assert.ok(insertSym);

    const detail = await getShowcaseSymbolDetail(1, insertSym.id);
    assert.strictEqual(detail.id, insertSym.id);
    assert.strictEqual(detail.name, "insert");
    assert.ok(detail.docstring?.includes("Insert a new document"));
    assert.ok(detail.source_excerpt?.includes("def insert"));
    assert.ok(detail.outgoing_relationships.length >= 2);
  });

  test("getShowcaseRelationships returns 226 call relationships", async () => {
    const rels = await getShowcaseRelationships();
    assert.strictEqual(rels.length, 226);
    assert.ok(rels.every((r) => r.relationship_type === "calls"));
    assert.ok(rels.every((r) => r.source_line !== null && r.source_line! > 0));
  });

  test("getShowcaseTrace reconstructs static AST call graph", async () => {
    const trace = await getShowcaseTrace(1, "tinydb.table.Table.insert");
    assert.strictEqual(trace.start_symbol, "tinydb.table.Table.insert");
    assert.ok(trace.nodes.length >= 3);
    assert.ok(trace.edges.length >= 2);
    assert.ok(trace.summary.includes("Table.insert"));
  });

  test("getShowcaseExplain returns precomputed traces for positive benchmark questions", async () => {
    const res = await getShowcaseExplain(
      1,
      "How does table insertion persist a new document in TinyDB?"
    );
    assert.ok(res.answer.includes("Table.insert"));
    assert.ok(res.trace !== null);
    assert.strictEqual(res.trace?.start_symbol, "tinydb.table.Table.insert");
    assert.ok(res.evidence.length > 0);
  });

  test("getShowcaseExplain gracefully refuses negative out-of-domain questions", async () => {
    const res = await getShowcaseExplain(1, "How does OAuth2 authentication login work?");
    assert.ok(res.answer.includes("couldn't determine this confidently"));
    assert.strictEqual(res.trace, null);
    assert.strictEqual(res.evidence.length, 0);
  });

  test("getShowcaseBenchmarkQueries returns all 13 verified benchmark queries", () => {
    const queries = getShowcaseBenchmarkQueries();
    assert.strictEqual(queries.length, 13);

    const positive = queries.filter((q) => !q.is_negative);
    const negative = queries.filter((q) => q.is_negative);
    assert.strictEqual(positive.length, 10);
    assert.strictEqual(negative.length, 3);
  });

  test("initial showcase synchronous getters return populated TinyDB data when showcase is active", () => {
    const orig = process.env.NEXT_PUBLIC_SHOWCASE_MODE;
    try {
      // 1. In disabled mode
      delete process.env.NEXT_PUBLIC_SHOWCASE_MODE;
      assert.deepStrictEqual(getInitialShowcaseRepoStatus(), []);
      assert.strictEqual(getInitialShowcaseSelectedRepoId(), null);
      assert.deepStrictEqual(getInitialShowcaseFiles(), []);
      assert.deepStrictEqual(getInitialShowcaseSymbols(), []);
      assert.deepStrictEqual(getInitialShowcaseRelationships(), []);

      // 2. In enabled mode
      process.env.NEXT_PUBLIC_SHOWCASE_MODE = "true";
      const repos = getInitialShowcaseRepoStatus();
      assert.strictEqual(repos.length, 1);
      assert.strictEqual(repos[0].repository.id, 1);
      assert.strictEqual(repos[0].repository.name, "tinydb");
      assert.strictEqual(repos[0].isIndexed, true);
      assert.strictEqual(repos[0].symbolCount, 314);
      assert.strictEqual(repos[0].fileCount, 21);

      assert.strictEqual(getInitialShowcaseSelectedRepoId(), 1);

      const files = getInitialShowcaseFiles();
      assert.strictEqual(files.length, 21);
      assert.ok(files.some((f) => f.relative_path.includes("tinydb/database.py")));

      const symbols = getInitialShowcaseSymbols();
      assert.strictEqual(symbols.length, 314);
      assert.ok(symbols.some((s) => s.qualified_name === "tinydb.table.Table.insert"));

      const rels = getInitialShowcaseRelationships();
      assert.strictEqual(rels.length, 226);
      assert.ok(rels.every((r) => r.relationship_type.toLowerCase() === "calls"));
    } finally {
      process.env.NEXT_PUBLIC_SHOWCASE_MODE = orig;
    }
  });
});

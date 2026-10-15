import test, { describe } from "node:test";
import assert from "node:assert/strict";
import {
  extractCallSubgraph,
  filterCallRelationships,
} from "./graph-utils.ts";
import type { CodeRelationship, CodeSymbol } from "../types/api.ts";

describe("Call Graph Data & Subgraph Extraction", () => {
  const sampleRelationships: CodeRelationship[] = [
    {
      id: 1,
      repository_id: 1,
      relationship_type: "contains",
      source_line: null,
      source_symbol: { id: 10, name: "Table", qualified_name: "tinydb.table.Table", symbol_type: "class" },
      target_symbol: { id: 101, name: "insert", qualified_name: "tinydb.table.Table.insert", symbol_type: "method" },
      created_at: "2026-10-12T00:00:00Z",
    },
    {
      id: 2,
      repository_id: 1,
      relationship_type: "calls",
      source_line: 145,
      source_symbol: { id: 101, name: "insert", qualified_name: "tinydb.table.Table.insert", symbol_type: "method" },
      target_symbol: { id: 102, name: "write", qualified_name: "tinydb.storages.Storage.write", symbol_type: "method" },
      created_at: "2026-10-12T00:00:00Z",
    },
    {
      id: 3,
      repository_id: 1,
      relationship_type: "calls",
      source_line: 150,
      source_symbol: { id: 101, name: "insert", qualified_name: "tinydb.table.Table.insert", symbol_type: "method" },
      target_symbol: { id: 103, name: "_get_next_id", qualified_name: "tinydb.table.Table._get_next_id", symbol_type: "method" },
      created_at: "2026-10-12T00:00:00Z",
    },
    {
      id: 4,
      repository_id: 1,
      relationship_type: "calls",
      source_line: 80,
      source_symbol: { id: 201, name: "insert_multiple", qualified_name: "tinydb.table.Table.insert_multiple", symbol_type: "method" },
      target_symbol: { id: 101, name: "insert", qualified_name: "tinydb.table.Table.insert", symbol_type: "method" },
      created_at: "2026-10-12T00:00:00Z",
    },
    {
      id: 5,
      repository_id: 1,
      relationship_type: "calls",
      source_line: 210,
      source_symbol: { id: 102, name: "write", qualified_name: "tinydb.storages.Storage.write", symbol_type: "method" },
      target_symbol: { id: 301, name: "dump", qualified_name: "json.dump", symbol_type: "function" },
      created_at: "2026-10-12T00:00:00Z",
    },
  ];

  const sampleSymbols: CodeSymbol[] = [
    {
      id: 101,
      file_id: 1,
      relative_path: "tinydb/table.py",
      name: "insert",
      qualified_name: "tinydb.table.Table.insert",
      symbol_type: "method",
      line_start: 140,
      line_end: 160,
      signature: "def insert(self, document: Mapping) -> int",
      docstring: "Insert a document.",
      created_at: "2026-10-12T00:00:00Z",
    },
    {
      id: 102,
      file_id: 2,
      relative_path: "tinydb/storages.py",
      name: "write",
      qualified_name: "tinydb.storages.Storage.write",
      symbol_type: "method",
      line_start: 50,
      line_end: 70,
      signature: "def write(self, data: dict) -> None",
      docstring: "Write data.",
      created_at: "2026-10-12T00:00:00Z",
    },
  ];

  test("filterCallRelationships excludes non-calls relationships", () => {
    const callOnly = filterCallRelationships(sampleRelationships);
    assert.strictEqual(callOnly.length, 4);
    assert.ok(callOnly.every((r) => r.relationship_type.toLowerCase() === "calls"));
  });

  test("extractCallSubgraph returns empty result when no CALLS relationships exist", () => {
    const result = extractCallSubgraph([]);
    assert.strictEqual(result.nodes.length, 0);
    assert.strictEqual(result.edges.length, 0);
    assert.strictEqual(result.totalCallEdges, 0);
  });

  test("extractCallSubgraph correctly identifies direct callers and callees around focused symbol", () => {
    const result = extractCallSubgraph(sampleRelationships, sampleSymbols, {
      focusedSymbolId: 101,
      depth: 1,
      maxNodes: 25,
    });

    assert.strictEqual(result.focusedSymbolId, 101);
    // Direct caller of 101 is 201 (insert_multiple)
    assert.ok(result.directCallerIds.has(201));
    // Direct callees of 101 are 102 (write) and 103 (_get_next_id)
    assert.ok(result.directCalleeIds.has(102));
    assert.ok(result.directCalleeIds.has(103));

    // Nodes contain focused, caller, and callees
    const focusedNode = result.nodes.find((n) => n.symbolId === 101);
    assert.ok(focusedNode);
    assert.strictEqual(focusedNode.role, "selected");
    assert.strictEqual(focusedNode.relativePath, "tinydb/table.py");

    const callerNode = result.nodes.find((n) => n.symbolId === 201);
    assert.ok(callerNode);
    assert.strictEqual(callerNode.role, "caller");

    const calleeNode = result.nodes.find((n) => n.symbolId === 102);
    assert.ok(calleeNode);
    assert.strictEqual(calleeNode.role, "callee");
  });

  test("extractCallSubgraph enforces maxNodes limit", () => {
    const result = extractCallSubgraph(sampleRelationships, sampleSymbols, {
      focusedSymbolId: 101,
      maxNodes: 2,
    });

    assert.ok(result.nodes.length <= 2);
  });

  test("extractCallSubgraph includes 2-hop callees when depth is 2", () => {
    const result1Hop = extractCallSubgraph(sampleRelationships, sampleSymbols, {
      focusedSymbolId: 101,
      depth: 1,
      maxNodes: 25,
    });
    // 301 (json.dump) is a callee of 102 (write), so 2-hop from 101
    assert.strictEqual(result1Hop.nodes.some((n) => n.symbolId === 301), false);

    const result2Hop = extractCallSubgraph(sampleRelationships, sampleSymbols, {
      focusedSymbolId: 101,
      depth: 2,
      maxNodes: 25,
    });
    assert.strictEqual(result2Hop.nodes.some((n) => n.symbolId === 301), true);
  });

  test("extractCallSubgraph automatically picks the top hub symbol when focus is not specified", () => {
    const result = extractCallSubgraph(sampleRelationships, sampleSymbols);
    // Symbol 101 has 1 incoming and 2 outgoing (total degree 3, highest in dataset)
    assert.strictEqual(result.focusedSymbolId, 101);
    assert.ok(result.nodes.length > 0);
  });

  test("extractCallSubgraph includes, numbers, and highlights architecture trace nodes and edges", () => {
    const traceNodes = [
      {
        step: 1,
        qualified_name: "tinydb.table.Table.insert",
        name: "insert",
        symbol_type: "method",
        file: "tinydb/table.py",
      },
      {
        step: 2,
        qualified_name: "tinydb.storages.Storage.write",
        name: "write",
        symbol_type: "method",
        file: "tinydb/storages.py",
      },
      {
        step: 3,
        qualified_name: "json.dump",
        name: "dump",
        symbol_type: "function",
        file: "json/__init__.py",
      },
    ];

    const traceEdges = [
      {
        from: "tinydb.table.Table.insert",
        to: "tinydb.storages.Storage.write",
        relationship: "calls",
        source_line: 145,
      },
      {
        from: "tinydb.storages.Storage.write",
        to: "json.dump",
        relationship: "calls",
        source_line: 210,
      },
    ];

    const result = extractCallSubgraph(sampleRelationships, sampleSymbols, {
      traceNodes,
      traceEdges,
      traceStartSymbol: "tinydb.table.Table.insert",
    });

    // All trace nodes are present
    assert.strictEqual(result.nodes.length >= 3, true);

    const startNode = result.nodes.find((n) => n.qualifiedName === "tinydb.table.Table.insert");
    assert.ok(startNode);
    assert.strictEqual(startNode.role, "trace-start");
    assert.strictEqual(startNode.traceStep, 1);

    const step2Node = result.nodes.find((n) => n.qualifiedName === "tinydb.storages.Storage.write");
    assert.ok(step2Node);
    assert.strictEqual(step2Node.role, "trace");
    assert.strictEqual(step2Node.traceStep, 2);

    const step3Node = result.nodes.find((n) => n.qualifiedName === "json.dump");
    assert.ok(step3Node);
    assert.strictEqual(step3Node.role, "trace");
    assert.strictEqual(step3Node.traceStep, 3);

    // Edges connecting trace nodes are marked isTraceEdge
    const traceEdge1 = result.edges.find(
      (e) => e.source === String(startNode.symbolId) && e.target === String(step2Node.symbolId)
    );
    assert.ok(traceEdge1);
    assert.strictEqual(traceEdge1.isTraceEdge, true);
    assert.strictEqual(traceEdge1.isHighlighted, true);
  });

  test("computeTraceNodeLayout preserves branching relationships without flattening", () => {
    // Branched execution flow:
    // Root: A
    // Branch 1: A -> B -> C
    // Branch 2: A -> D -> E
    const traceNodes = [
      { step: 1, qualified_name: "pkg.mod.A", name: "A", symbol_type: "method" },
      { step: 2, qualified_name: "pkg.mod.B", name: "B", symbol_type: "method" },
      { step: 3, qualified_name: "pkg.mod.C", name: "C", symbol_type: "method" },
      { step: 4, qualified_name: "pkg.mod.D", name: "D", symbol_type: "method" },
      { step: 5, qualified_name: "pkg.mod.E", name: "E", symbol_type: "method" },
    ];
    const traceEdges = [
      { from: "pkg.mod.A", to: "pkg.mod.B", relationship: "calls", source_line: 10 },
      { from: "pkg.mod.B", to: "pkg.mod.C", relationship: "calls", source_line: 20 },
      { from: "pkg.mod.A", to: "pkg.mod.D", relationship: "calls", source_line: 30 },
      { from: "pkg.mod.D", to: "pkg.mod.E", relationship: "calls", source_line: 40 },
    ];

    const result = extractCallSubgraph([], [], {
      traceNodes,
      traceEdges,
      traceStartSymbol: "pkg.mod.A",
    });

    const nodeA = result.nodes.find((n) => n.qualifiedName === "pkg.mod.A")!;
    const nodeB = result.nodes.find((n) => n.qualifiedName === "pkg.mod.B")!;
    const nodeC = result.nodes.find((n) => n.qualifiedName === "pkg.mod.C")!;
    const nodeD = result.nodes.find((n) => n.qualifiedName === "pkg.mod.D")!;
    const nodeE = result.nodes.find((n) => n.qualifiedName === "pkg.mod.E")!;

    // Root node is at rank depth 0
    assert.strictEqual(nodeA.position.x, 50);

    // Branch 1 and Branch 2 children (B and D) are both at depth 1 (same x), but in different lanes (different y)
    assert.strictEqual(nodeB.position.x, nodeD.position.x);
    assert.notStrictEqual(nodeB.position.y, nodeD.position.y);

    // Sub-callees C and E are both at depth 2 (same x), but in different lanes (different y)
    assert.strictEqual(nodeC.position.x, nodeE.position.x);
    assert.notStrictEqual(nodeC.position.y, nodeE.position.y);
    assert.strictEqual(nodeC.position.y, nodeB.position.y); // C follows B's lane
    assert.strictEqual(nodeE.position.y, nodeD.position.y); // E follows D's lane

    // Verify no spurious edge between sibling branches C and D
    const falseEdge = result.edges.find(
      (e) => (e.source === String(nodeC.symbolId) && e.target === String(nodeD.symbolId)) ||
             (e.source === String(nodeB.symbolId) && e.target === String(nodeD.symbolId))
    );
    assert.strictEqual(falseEdge, undefined);
  });

  test("extractCallSubgraph does not mark unrelated repository edges as trace edges when trace is active", () => {
    // In repository, there is an unrelated call from dump to another function
    const relationshipsWithUnrelated: CodeRelationship[] = [
      ...sampleRelationships,
      {
        id: 99,
        repository_id: 1,
        relationship_type: "calls",
        source_line: 999,
        source_symbol: { id: 301, name: "dump", qualified_name: "json.dump", symbol_type: "function" },
        target_symbol: { id: 103, name: "_get_next_id", qualified_name: "tinydb.table.Table._get_next_id", symbol_type: "method" },
        created_at: "2026-10-12T00:00:00Z",
      },
    ];

    const traceNodes = [
      { step: 1, qualified_name: "tinydb.table.Table.insert", name: "insert", symbol_type: "method" },
      { step: 2, qualified_name: "tinydb.storages.Storage.write", name: "write", symbol_type: "method" },
    ];
    const traceEdges = [
      { from: "tinydb.table.Table.insert", to: "tinydb.storages.Storage.write", relationship: "calls", source_line: 145 },
    ];

    const result = extractCallSubgraph(relationshipsWithUnrelated, sampleSymbols, {
      traceNodes,
      traceEdges,
      traceStartSymbol: "tinydb.table.Table.insert",
    });

    // Only the explicit trace edge is flagged as isTraceEdge
    const traceEdgesResult = result.edges.filter((e) => e.isTraceEdge);
    assert.strictEqual(traceEdgesResult.length, 1);
    assert.strictEqual(traceEdgesResult[0].sourceLine, 145);
  });
});

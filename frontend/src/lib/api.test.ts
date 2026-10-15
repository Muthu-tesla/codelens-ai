import test, { describe } from "node:test";
import assert from "node:assert/strict";
import {
  ApiError,
  createRepository,
  explainArchitecture,
  getRepository,
  getRepositoryFiles,
  getRepositoryRelationships,
  getRepositorySymbols,
  traceArchitecture,
} from "./api.ts";

describe("Frontend API Client", () => {
  test("ApiError correctly preserves status, message, and error details", () => {
    const error = new ApiError("Repository not found", 404, { detail: "Repository not found" });
    assert.strictEqual(error.name, "ApiError");
    assert.strictEqual(error.status, 404);
    assert.strictEqual(error.message, "Repository not found");
    assert.deepStrictEqual(error.data, { detail: "Repository not found" });
  });

  test("getRepository fetches repository details using correct endpoint and headers", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        assert.ok(String(url).endsWith("/repositories/1"));
        const headers = init?.headers as Record<string, string> | undefined;
        assert.strictEqual(headers?.["Accept"], "application/json");
        return new Response(
          JSON.stringify({
            id: 1,
            name: "tinydb",
            path: "/path/to/tinydb",
            created_at: "2026-10-12T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const repo = await getRepository(1);
      assert.strictEqual(repo.id, 1);
      assert.strictEqual(repo.name, "tinydb");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("getRepositorySymbols constructs correct query parameters", async () => {
    const originalFetch = globalThis.fetch;
    try {
      let requestedUrl = "";
      globalThis.fetch = async (url: string | URL | Request) => {
        requestedUrl = String(url);
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      await getRepositorySymbols(42, { symbolType: "class", search: "Table" });
      assert.ok(requestedUrl.includes("/repositories/42/symbols?"));
      assert.ok(requestedUrl.includes("symbol_type=class"));
      assert.ok(requestedUrl.includes("search=Table"));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("createRepository issues POST request with json payload", async () => {
    const originalFetch = globalThis.fetch;
    try {
      let sentBody = "";
      let sentMethod = "";
      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        sentMethod = init?.method || "";
        sentBody = String(init?.body);
        return new Response(
          JSON.stringify({
            id: 2,
            name: "testrepo",
            path: "evaluation_repos/tinydb",
            created_at: "2026-10-12T00:00:00Z",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } }
        );
      };

      const result = await createRepository({
        name: "testrepo",
        path: "evaluation_repos/tinydb",
      });
      assert.strictEqual(sentMethod, "POST");
      assert.strictEqual(
        sentBody,
        JSON.stringify({ name: "testrepo", path: "evaluation_repos/tinydb" })
      );
      assert.strictEqual(result.id, 2);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("handleResponse throws ApiError on non-200 responses with backend detail", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => {
        return new Response(
          JSON.stringify({ detail: "Repository path does not exist: /invalid/path" }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      };

      await assert.rejects(
        async () => {
          await getRepositoryFiles(999);
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError);
          assert.strictEqual(err.status, 400);
          assert.strictEqual(err.message, "Repository path does not exist: /invalid/path");
          return true;
        }
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("getRepositoryRelationships queries correct endpoint with relationship_type filter", async () => {
    const originalFetch = globalThis.fetch;
    try {
      let requestedUrl = "";
      globalThis.fetch = async (url: string | URL | Request) => {
        requestedUrl = String(url);
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      };

      await getRepositoryRelationships(15, "calls");
      assert.ok(requestedUrl.includes("/repositories/15/relationships?"));
      assert.ok(requestedUrl.includes("relationship_type=calls"));
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("traceArchitecture issues POST request with start_symbol payload", async () => {
    const originalFetch = globalThis.fetch;
    try {
      let sentUrl = "";
      let sentBody = "";
      let sentMethod = "";

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        sentUrl = String(url);
        sentMethod = init?.method || "";
        sentBody = String(init?.body);
        return new Response(
          JSON.stringify({
            start_symbol: "tinydb.table.Table.insert",
            nodes: [
              {
                step: 1,
                qualified_name: "tinydb.table.Table.insert",
                name: "insert",
                symbol_type: "method",
                file: "tinydb/table.py",
              },
            ],
            edges: [],
            summary: "Traced 1 node.",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const res = await traceArchitecture(1, "tinydb.table.Table.insert");
      assert.ok(sentUrl.endsWith("/repositories/1/architecture/trace"));
      assert.strictEqual(sentMethod, "POST");
      assert.strictEqual(sentBody, JSON.stringify({ start_symbol: "tinydb.table.Table.insert" }));
      assert.strictEqual(res.start_symbol, "tinydb.table.Table.insert");
      assert.strictEqual(res.nodes.length, 1);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("explainArchitecture issues POST request with question payload", async () => {
    const originalFetch = globalThis.fetch;
    try {
      let sentUrl = "";
      let sentBody = "";
      let sentMethod = "";

      globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
        sentUrl = String(url);
        sentMethod = init?.method || "";
        sentBody = String(init?.body);
        return new Response(
          JSON.stringify({
            question: "How does table insertion persist a document?",
            answer: "Insertion calls storage.write [E1].",
            trace: {
              start_symbol: "tinydb.table.Table.insert",
              nodes: [
                {
                  step: 1,
                  qualified_name: "tinydb.table.Table.insert",
                  name: "insert",
                  symbol_type: "method",
                  file: "tinydb/table.py",
                },
              ],
              edges: [],
            },
            evidence: [
              {
                id: "E1",
                file: "tinydb/table.py",
                content: "def insert(): pass",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const res = await explainArchitecture(1, "How does table insertion persist a document?");
      assert.ok(sentUrl.endsWith("/repositories/1/architecture/explain"));
      assert.strictEqual(sentMethod, "POST");
      assert.strictEqual(
        sentBody,
        JSON.stringify({ question: "How does table insertion persist a document?" })
      );
      assert.ok(res.answer.includes("[E1]"));
      assert.strictEqual(res.evidence.length, 1);
      assert.strictEqual(res.trace?.start_symbol, "tinydb.table.Table.insert");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

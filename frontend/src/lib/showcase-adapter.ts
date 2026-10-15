import type {
  ArchitectureExplainResponse,
  ArchitectureTraceResponse,
  CodeRelationship,
  CodeSymbol,
  CodeSymbolDetail,
  FileMetadata,
  Repository,
  RepositoryFilesResponse,
} from "../types/api.ts";
import type { ListSymbolsOptions } from "./api.ts";

import repositoryData from "../data/showcase/repository.json" with { type: "json" };
import filesData from "../data/showcase/files.json" with { type: "json" };
import symbolsData from "../data/showcase/symbols.json" with { type: "json" };
import symbolDetailsData from "../data/showcase/symbol_details.json" with { type: "json" };
import relationshipsData from "../data/showcase/relationships.json" with { type: "json" };
import tracesData from "../data/showcase/traces.json" with { type: "json" };

/**
 * Custom error class for showcase data issues.
 */
export class ShowcaseDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ShowcaseDataError";
  }
}

/**
 * Determine if showcase mode is active via NEXT_PUBLIC_SHOWCASE_MODE environment variable.
 * Accepts "true" or "1". Unset, empty, or other values return false.
 */
export function isShowcaseMode(): boolean {
  const envVal = process.env.NEXT_PUBLIC_SHOWCASE_MODE;
  return envVal === "true" || envVal === "1";
}

/**
 * Validate integrity and presence of the 6 precomputed showcase datasets.
 */
export function validateShowcaseData(): { isValid: boolean; error: string | null } {
  try {
    if (!repositoryData || typeof repositoryData !== "object" || !("id" in repositoryData)) {
      return { isValid: false, error: "Showcase repository.json is missing or malformed." };
    }
    if (!Array.isArray(filesData) || filesData.length === 0) {
      return { isValid: false, error: "Showcase files.json is missing or empty." };
    }
    if (!Array.isArray(symbolsData) || symbolsData.length === 0) {
      return { isValid: false, error: "Showcase symbols.json is missing or empty." };
    }
    if (!symbolDetailsData || typeof symbolDetailsData !== "object") {
      return { isValid: false, error: "Showcase symbol_details.json is missing or malformed." };
    }
    if (!Array.isArray(relationshipsData)) {
      return { isValid: false, error: "Showcase relationships.json is missing or malformed." };
    }
    if (!tracesData || typeof tracesData !== "object" || !("provenance" in tracesData)) {
      return { isValid: false, error: "Showcase traces.json is missing or malformed." };
    }
    return { isValid: true, error: null };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Unknown validation failure";
    return { isValid: false, error: `Showcase validation exception: ${msg}` };
  }
}

/**
 * Health check in showcase mode (purely local, 0 network requests).
 */
export async function checkShowcaseHealth(): Promise<{ status: string; service: string }> {
  const validation = validateShowcaseData();
  if (!validation.isValid) {
    throw new ShowcaseDataError(validation.error || "Showcase data corrupted");
  }
  return {
    status: "showcase",
    service: "CodeLens AI Static Showcase (TinyDB v4.8.2)",
  };
}

/**
 * Retrieve the showcase repository record.
 */
export async function getShowcaseRepository(id?: number): Promise<Repository> {
  const validation = validateShowcaseData();
  if (!validation.isValid) throw new ShowcaseDataError(validation.error!);

  if (id !== undefined && id !== repositoryData.id) {
    throw new ShowcaseDataError(`Repository ID ${id} not found in static showcase (only TinyDB #1 is available).`);
  }

  return {
    id: repositoryData.id,
    name: repositoryData.name,
    path: repositoryData.path,
    created_at: repositoryData.created_at,
  };
}

/**
 * Retrieve list of registered repositories in showcase mode (only TinyDB #1).
 */
export async function getShowcaseRepositories(): Promise<Repository[]> {
  const repo = await getShowcaseRepository();
  return [repo];
}

/**
 * Retrieve full metadata for showcase repository (attribution, stats, benchmark metrics).
 */
export function getShowcaseMetadata(): typeof repositoryData {
  return repositoryData;
}

/**
 * Retrieve all 21 discovered files for TinyDB showcase.
 */
export async function getShowcaseFiles(repositoryId?: number): Promise<RepositoryFilesResponse> {
  const validation = validateShowcaseData();
  if (!validation.isValid) throw new ShowcaseDataError(validation.error!);

  const targetRepoId = repositoryId || repositoryData.id;
  const filesList: FileMetadata[] = filesData.map((f) => ({
    relative_path: f.relative_path,
    extension: f.extension,
    size_bytes: f.size_bytes,
    line_count: f.line_count,
  }));

  return {
    repository_id: targetRepoId,
    total_files: filesList.length,
    files: filesList,
  };
}

/**
 * Retrieve and filter showcase symbols by symbol_type or search substring.
 */
export async function getShowcaseSymbols(
  repositoryId?: number,
  options?: ListSymbolsOptions
): Promise<CodeSymbol[]> {
  const validation = validateShowcaseData();
  if (!validation.isValid) throw new ShowcaseDataError(validation.error!);

  let list = symbolsData as unknown as CodeSymbol[];

  if (options?.symbolType && options.symbolType !== "all") {
    const targetType = options.symbolType.toLowerCase();
    list = list.filter((s) => s.symbol_type.toLowerCase() === targetType);
  }

  if (options?.search && options.search.trim()) {
    const query = options.search.trim().toLowerCase();
    list = list.filter(
      (s) =>
        s.name.toLowerCase().includes(query) ||
        s.qualified_name.toLowerCase().includes(query)
    );
  }

  return list;
}

/**
 * Retrieve detailed symbol record with docstrings, excerpts, and incoming/outgoing edges.
 */
export async function getShowcaseSymbolDetail(
  repositoryId: number,
  symbolId: number
): Promise<CodeSymbolDetail> {
  const validation = validateShowcaseData();
  if (!validation.isValid) throw new ShowcaseDataError(validation.error!);

  const key = String(symbolId);
  const detail = (symbolDetailsData as Record<string, unknown>)[key];

  if (!detail) {
    throw new ShowcaseDataError(`Symbol #${symbolId} not found in showcase repository.`);
  }

  return detail as unknown as CodeSymbolDetail;
}

/**
 * Retrieve AST call relationships for the showcase codebase.
 */
export async function getShowcaseRelationships(
  repositoryId?: number,
  relationshipType?: string
): Promise<CodeRelationship[]> {
  const validation = validateShowcaseData();
  if (!validation.isValid) throw new ShowcaseDataError(validation.error!);

  const list = relationshipsData as unknown as CodeRelationship[];

  if (relationshipType && relationshipType !== "all") {
    return list.filter(
      (r) => r.relationship_type.toLowerCase() === relationshipType.toLowerCase()
    );
  }

  return list;
}

/**
 * Deterministic architecture trace reconstruction in showcase mode.
 * Returns precomputed static AST traces without runtime execution.
 */
export async function getShowcaseTrace(
  repositoryId: number,
  startSymbol: string
): Promise<ArchitectureTraceResponse> {
  const validation = validateShowcaseData();
  if (!validation.isValid) throw new ShowcaseDataError(validation.error!);

  const cleanStart = startSymbol.trim();
  const symbolTraces = tracesData.symbol_traces as Record<string, ArchitectureTraceResponse>;

  if (symbolTraces[cleanStart]) {
    return symbolTraces[cleanStart];
  }

  // If the symbol exists in TinyDB but has 0 outgoing calls, construct a deterministic 1-node trace
  const existingSym = (symbolsData as unknown as CodeSymbol[]).find(
    (s) => s.qualified_name === cleanStart
  );

  if (existingSym) {
    return {
      start_symbol: cleanStart,
      nodes: [
        {
          step: 1,
          qualified_name: cleanStart,
          name: existingSym.name,
          symbol_type: existingSym.symbol_type,
          file: existingSym.relative_path || "",
          line_start: existingSym.line_start,
          line_end: existingSym.line_end,
          signature: existingSym.signature,
        },
      ],
      edges: [],
      summary: `Deterministic static AST traversal starting at '${cleanStart}' discovered 0 outgoing call relationships in TinyDB.`,
    };
  }

  throw new ShowcaseDataError(`Start symbol '${cleanStart}' not found in showcase repository.`);
}

/**
 * Architecture-aware codebase question explanation in showcase mode.
 * Matches questions against the 13 verified benchmark test cases.
 */
export async function getShowcaseExplain(
  repositoryId: number,
  question: string
): Promise<ArchitectureExplainResponse> {
  const validation = validateShowcaseData();
  if (!validation.isValid) throw new ShowcaseDataError(validation.error!);

  const cleanQ = question.trim().toLowerCase();
  const benchmarkQueries = tracesData.benchmark_queries;

  // 1. Direct exact or substring match on benchmark questions
  let matched = benchmarkQueries.find(
    (b) => b.question.toLowerCase() === cleanQ || cleanQ.includes(b.question.toLowerCase())
  );

  // 2. Keyword-based matching for natural variations of benchmark questions
  if (!matched) {
    if (cleanQ.includes("insert") || (cleanQ.includes("persist") && cleanQ.includes("document"))) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-01");
    } else if (cleanQ.includes("search") || cleanQ.includes("find document")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-02");
    } else if (cleanQ.includes("count")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-03");
    } else if (cleanQ.includes("truncate")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-04");
    } else if (cleanQ.includes("remove") || cleanQ.includes("delete matching")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-05");
    } else if (cleanQ.includes("write") || (cleanQ.includes("serialize") && cleanQ.includes("disk"))) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-06");
    } else if (cleanQ.includes("read") || cleanQ.includes("deserialize")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-07");
    } else if (cleanQ.includes("close")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-08");
    } else if (cleanQ.includes("touch") || cleanQ.includes("directory")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-09");
    } else if (cleanQ.includes("delete operation") || (cleanQ.includes("transform") && cleanQ.includes("field"))) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-10");
    } else if (cleanQ.includes("oauth") || cleanQ.includes("login") || cleanQ.includes("jwt")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-11");
    } else if (cleanQ.includes("kafka") || cleanQ.includes("streaming") || cleanQ.includes("consumer")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-12");
    } else if (cleanQ.includes("redis") || cleanQ.includes("cluster") || cleanQ.includes("pool")) {
      matched = benchmarkQueries.find((b) => b.id === "REAL-13");
    }
  }

  if (matched) {
    return {
      question: question.trim(),
      answer: matched.answer,
      trace: matched.trace
        ? {
            start_symbol: matched.trace.start_symbol,
            nodes: matched.trace.nodes,
            edges: matched.trace.edges,
          }
        : null,
      evidence: matched.evidence || [],
    };
  }

  // Graceful fallback for questions not in precomputed benchmark
  return {
    question: question.trim(),
    answer: (
      "I couldn't determine this confidently from the precomputed showcase data. " +
      "In ₹0 static showcase mode, queries are grounded in the 13 verified TinyDB benchmark test cases. " +
      "Select one of the verified benchmark queries or explore symbols directly in the Call Graph."
    ),
    trace: null,
    evidence: [],
  };
}

/**
 * Return list of the 13 verified benchmark queries for showcase UI suggestions.
 */
export function getShowcaseBenchmarkQueries(): Array<{
  id: string;
  question: string;
  category: string;
  is_negative: boolean;
  start_symbol: string | null;
}> {
  return tracesData.benchmark_queries.map((q) => ({
    id: q.id,
    question: q.question,
    category: q.category,
    is_negative: q.is_negative,
    start_symbol: q.resolved_start_symbol,
  }));
}

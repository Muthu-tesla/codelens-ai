import type {
  ArchitectureExplainResponse,
  ArchitectureTraceResponse,
  CodeRelationship,
  CodeSymbol,
  CodeSymbolDetail,
  Repository,
  RepositoryAnalysisSummary,
  RepositoryCreateInput,
  RepositoryFilesResponse,
} from "../types/api.ts";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = response.statusText;
    let errorData: unknown = null;
    try {
      errorData = await response.json();
      if (
        errorData &&
        typeof errorData === "object" &&
        "detail" in errorData &&
        typeof (errorData as { detail: unknown }).detail === "string"
      ) {
        errorDetail = (errorData as { detail: string }).detail;
      }
    } catch {
      // Ignore JSON parse error on non-JSON response
    }
    throw new ApiError(errorDetail || `Request failed with status ${response.status}`, response.status, errorData);
  }
  return response.json() as Promise<T>;
}

export async function checkBackendHealth(): Promise<{ status: string; service: string }> {
  const host = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  const res = await fetch(`${host}/health`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  return handleResponse<{ status: string; service: string }>(res);
}

export async function getRepositories(): Promise<Repository[]> {
  const res = await fetch(`${API_BASE_URL}/repositories`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  return handleResponse<Repository[]>(res);
}

export async function getRepository(id: number): Promise<Repository> {
  const res = await fetch(`${API_BASE_URL}/repositories/${id}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  return handleResponse<Repository>(res);
}

export async function createRepository(input: RepositoryCreateInput): Promise<Repository> {
  const res = await fetch(`${API_BASE_URL}/repositories`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(input),
  });
  return handleResponse<Repository>(res);
}

export async function getRepositoryFiles(repositoryId: number): Promise<RepositoryFilesResponse> {
  const res = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/files`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  return handleResponse<RepositoryFilesResponse>(res);
}

export async function analyzeRepository(repositoryId: number): Promise<RepositoryAnalysisSummary> {
  const res = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/analyze`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return handleResponse<RepositoryAnalysisSummary>(res);
}

export interface ListSymbolsOptions {
  symbolType?: string;
  search?: string;
}

export async function getRepositorySymbols(
  repositoryId: number,
  options?: ListSymbolsOptions
): Promise<CodeSymbol[]> {
  const params = new URLSearchParams();
  if (options?.symbolType && options.symbolType !== "all") {
    params.set("symbol_type", options.symbolType);
  }
  if (options?.search && options.search.trim()) {
    params.set("search", options.search.trim());
  }

  const queryString = params.toString();
  const url = `${API_BASE_URL}/repositories/${repositoryId}/symbols${queryString ? `?${queryString}` : ""}`;

  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  return handleResponse<CodeSymbol[]>(res);
}

export async function getSymbolDetail(
  repositoryId: number,
  symbolId: number
): Promise<CodeSymbolDetail> {
  const res = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/symbols/${symbolId}`,
    {
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );
  return handleResponse<CodeSymbolDetail>(res);
}

export async function getRepositoryRelationships(
  repositoryId: number,
  relationshipType?: string
): Promise<CodeRelationship[]> {
  const params = new URLSearchParams();
  if (relationshipType) {
    params.set("relationship_type", relationshipType);
  }
  const queryString = params.toString();
  const url = `${API_BASE_URL}/repositories/${repositoryId}/relationships${queryString ? `?${queryString}` : ""}`;

  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  return handleResponse<CodeRelationship[]>(res);
}

export async function traceArchitecture(
  repositoryId: number,
  startSymbol: string
): Promise<ArchitectureTraceResponse> {
  const res = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/architecture/trace`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ start_symbol: startSymbol }),
    }
  );
  return handleResponse<ArchitectureTraceResponse>(res);
}

export async function explainArchitecture(
  repositoryId: number,
  question: string
): Promise<ArchitectureExplainResponse> {
  const res = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/architecture/explain`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ question }),
    }
  );
  return handleResponse<ArchitectureExplainResponse>(res);
}


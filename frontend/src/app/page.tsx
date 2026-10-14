"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  ArchitectureTraceEdge,
  ArchitectureTraceNode,
  CodeRelationship,
  CodeSymbol,
  CodeSymbolDetail,
  FileMetadata,
  RepositoryCreateInput,
  RepositoryStatus,
} from "@/types/api";
import {
  analyzeRepository,
  checkBackendHealth,
  createRepository,
  getRepositories,
  getRepositoryFiles,
  getRepositoryRelationships,
  getRepositorySymbols,
  getSymbolDetail,
} from "@/lib/api";
import { Header } from "@/components/Header";
import { RegisterModal } from "@/components/RegisterModal";
import { RepositoryList } from "@/components/RepositoryList";
import { FileExplorer } from "@/components/FileExplorer";
import { SymbolExplorer } from "@/components/SymbolExplorer";
import { SymbolDetailView } from "@/components/SymbolDetailView";
import { CallGraphView } from "@/components/CallGraphView";
import { ArchitectureTracePanel } from "@/components/ArchitectureTracePanel";
import { ErrorAlert } from "@/components/ErrorAlert";

export default function DashboardPage() {
  // Global & API state
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Repository state
  const [reposStatus, setReposStatus] = useState<RepositoryStatus[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<number | null>(null);
  const [isLoadingRepos, setIsLoadingRepos] = useState(true);

  // Files & Explorer state
  const [files, setFiles] = useState<FileMetadata[]>([]);
  const [selectedFileFilter, setSelectedFileFilter] = useState<string | null>(null);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [leftTab, setLeftTab] = useState<"explorer" | "repos">("explorer");

  // Center view mode (Explorer vs Interactive Call Graph)
  const [centerTab, setCenterTab] = useState<"symbols" | "graph">("symbols");

  // Right column tab (Symbol Inspector vs Architecture Trace)
  const [rightTab, setRightTab] = useState<"inspector" | "trace">("inspector");

  // Symbols state
  const [symbols, setSymbols] = useState<CodeSymbol[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedType, setSelectedType] = useState("all");
  const [isLoadingSymbols, setIsLoadingSymbols] = useState(false);

  // Relationships (Call Graph) state
  const [callRelationships, setCallRelationships] = useState<CodeRelationship[]>([]);
  const [isLoadingRelationships, setIsLoadingRelationships] = useState(false);
  const [relationshipsError, setRelationshipsError] = useState<string | null>(null);

  // Architecture Trace state
  const [activeTrace, setActiveTrace] = useState<{
    nodes: ArchitectureTraceNode[];
    edges: ArchitectureTraceEdge[];
    startSymbol: string;
  } | null>(null);

  // Symbol Detail state
  const [selectedSymbolId, setSelectedSymbolId] = useState<number | null>(null);
  const [symbolDetail, setSymbolDetail] = useState<CodeSymbolDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  // Active repo object
  const activeRepoStatus = reposStatus.find((r) => r.repository.id === selectedRepoId);
  const activeRepo = activeRepoStatus?.repository || null;
  const isIndexed = activeRepoStatus?.isIndexed ?? false;

  // 1. Health check
  const pingHealth = useCallback(async () => {
    try {
      await checkBackendHealth();
      setBackendHealthy(true);
    } catch {
      setBackendHealthy(false);
    }
  }, []);

  // 2. Load repositories & compute indexed status
  const loadRepositories = useCallback(
    async (selectId?: number) => {
      setIsLoadingRepos(true);
      try {
        const repos = await getRepositories();
        setBackendHealthy(true);

        const statusList: RepositoryStatus[] = await Promise.all(
          repos.map(async (repo) => {
            try {
              const [syms, fileRes] = await Promise.all([
                getRepositorySymbols(repo.id).catch(() => []),
                getRepositoryFiles(repo.id).catch(() => ({ total_files: 0, files: [] })),
              ]);
              return {
                repository: repo,
                isIndexed: syms.length > 0,
                symbolCount: syms.length,
                fileCount: fileRes.total_files || fileRes.files.length || 0,
              };
            } catch {
              return {
                repository: repo,
                isIndexed: false,
                symbolCount: 0,
                fileCount: 0,
              };
            }
          })
        );

        setReposStatus(statusList);

        if (statusList.length > 0) {
          const nextSelectedId =
            selectId ||
            (selectedRepoId && statusList.some((r) => r.repository.id === selectedRepoId)
              ? selectedRepoId
              : statusList[0].repository.id);
          setSelectedRepoId(nextSelectedId);
        } else {
          setSelectedRepoId(null);
        }
      } catch (err: unknown) {
        setBackendHealthy(false);
        const msg = err instanceof Error ? err.message : "Failed to load repositories";
        setErrorMessage(msg);
      } finally {
        setIsLoadingRepos(false);
      }
    },
    [selectedRepoId]
  );

  // 3. Load repository files
  const loadFiles = useCallback(async (repoId: number) => {
    setIsLoadingFiles(true);
    try {
      const data = await getRepositoryFiles(repoId);
      setFiles(data.files || []);
    } catch {
      setFiles([]);
    } finally {
      setIsLoadingFiles(false);
    }
  }, []);

  // 4. Load repository symbols with filters
  const loadSymbols = useCallback(
    async (repoId: number, type: string, search: string) => {
      setIsLoadingSymbols(true);
      try {
        const syms = await getRepositorySymbols(repoId, {
          symbolType: type,
          search: search,
        });
        setSymbols(syms || []);
      } catch {
        setSymbols([]);
      } finally {
        setIsLoadingSymbols(false);
      }
    },
    []
  );

  // 5. Load CALLS relationships for the graph
  const loadRelationships = useCallback(async (repoId: number) => {
    setIsLoadingRelationships(true);
    setRelationshipsError(null);
    try {
      const rels = await getRepositoryRelationships(repoId, "calls");
      setCallRelationships(rels || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load function call graph data";
      setRelationshipsError(msg);
      setCallRelationships([]);
    } finally {
      setIsLoadingRelationships(false);
    }
  }, []);

  // 6. Load symbol detail
  const loadDetail = useCallback(async (repoId: number, symbolId: number) => {
    setIsLoadingDetail(true);
    try {
      const detail = await getSymbolDetail(repoId, symbolId);
      setSymbolDetail(detail);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load symbol detail";
      setErrorMessage(msg);
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const [prevSelectedRepoId, setPrevSelectedRepoId] = useState<number | null>(selectedRepoId);

  // When selected repository changes, reset selections during render
  if (selectedRepoId !== prevSelectedRepoId) {
    setPrevSelectedRepoId(selectedRepoId);
    setSelectedFileFilter(null);
    setSelectedSymbolId(null);
    setSymbolDetail(null);
    setActiveTrace(null);
    if (!selectedRepoId) {
      setFiles([]);
      setSymbols([]);
      setCallRelationships([]);
    }
  }

  // Initial load
  useEffect(() => {
    let ignore = false;
    async function init() {
      try {
        await checkBackendHealth();
        if (!ignore) setBackendHealthy(true);
      } catch {
        if (!ignore) setBackendHealthy(false);
      }

      try {
        const repos = await getRepositories();
        if (ignore) return;
        setBackendHealthy(true);

        const statusList: RepositoryStatus[] = await Promise.all(
          repos.map(async (repo) => {
            try {
              const [syms, fileRes] = await Promise.all([
                getRepositorySymbols(repo.id).catch(() => []),
                getRepositoryFiles(repo.id).catch(() => ({ total_files: 0, files: [] })),
              ]);
              return {
                repository: repo,
                isIndexed: syms.length > 0,
                symbolCount: syms.length,
                fileCount: fileRes.total_files || fileRes.files.length || 0,
              };
            } catch {
              return {
                repository: repo,
                isIndexed: false,
                symbolCount: 0,
                fileCount: 0,
              };
            }
          })
        );

        if (ignore) return;
        setReposStatus(statusList);

        if (statusList.length > 0) {
          setSelectedRepoId((curr) =>
            curr && statusList.some((r) => r.repository.id === curr)
              ? curr
              : statusList[0].repository.id
          );
        } else {
          setSelectedRepoId(null);
        }
      } catch (err: unknown) {
        if (ignore) return;
        setBackendHealthy(false);
        const msg = err instanceof Error ? err.message : "Failed to load repositories";
        setErrorMessage(msg);
      } finally {
        if (!ignore) setIsLoadingRepos(false);
      }
    }

    init();
    return () => {
      ignore = true;
    };
  }, []);

  // When active repository or query filters change, fetch repository data
  useEffect(() => {
    if (!selectedRepoId) return;
    let ignore = false;

    async function fetchRepoData() {
      try {
        const [filesRes, symsRes, relsRes] = await Promise.all([
          getRepositoryFiles(selectedRepoId!).catch(() => ({ total_files: 0, files: [] })),
          getRepositorySymbols(selectedRepoId!, {
            symbolType: selectedType,
            search: searchQuery,
          }).catch(() => []),
          getRepositoryRelationships(selectedRepoId!, "calls").catch((err: unknown) => {
            const msg = err instanceof Error ? err.message : "Failed to load function call graph data";
            if (!ignore) setRelationshipsError(msg);
            return [];
          }),
        ]);

        if (!ignore) {
          setFiles(filesRes.files || []);
          setSymbols(symsRes || []);
          setCallRelationships(relsRes || []);
          setRelationshipsError(null);
        }
      } finally {
        if (!ignore) {
          setIsLoadingFiles(false);
          setIsLoadingSymbols(false);
          setIsLoadingRelationships(false);
        }
      }
    }

    fetchRepoData();

    return () => {
      ignore = true;
    };
  }, [selectedRepoId, selectedType, searchQuery]);

  // Debounce search/filter symbol reloads
  function handleSearchChange(q: string) {
    setSearchQuery(q);
    if (selectedRepoId) {
      loadSymbols(selectedRepoId, selectedType, q);
    }
  }

  function handleTypeChange(type: string) {
    setSelectedType(type);
    if (selectedRepoId) {
      loadSymbols(selectedRepoId, type, searchQuery);
    }
  }

  // Handle symbol selection
  function handleSelectSymbol(sym: CodeSymbol) {
    setSelectedSymbolId(sym.id);
    if (selectedRepoId) {
      loadDetail(selectedRepoId, sym.id);
    }
  }

  // Handle relationship link navigation
  function handleNavigateToSymbol(symbolId: number) {
    setSelectedSymbolId(symbolId);
    if (selectedRepoId) {
      loadDetail(selectedRepoId, symbolId);
    }
  }

  // Handle selecting node from trace sequence
  function handleSelectTraceNode(node: ArchitectureTraceNode) {
    const matched = symbols.find((s) => s.qualified_name === node.qualified_name);
    if (matched) {
      setSelectedSymbolId(matched.id);
      if (selectedRepoId) {
        loadDetail(selectedRepoId, matched.id);
      }
    }
  }

  // Handle architecture trace success
  function handleTraceSuccess(trace: {
    nodes: ArchitectureTraceNode[];
    edges: ArchitectureTraceEdge[];
    startSymbol: string;
  }) {
    setActiveTrace(trace);
    setCenterTab("graph"); // Switch center panel to call graph so user sees the highlighted path immediately
  }

  // Trigger AST Indexing
  async function handleAnalyze(repoId: number) {
    setReposStatus((prev) =>
      prev.map((r) =>
        r.repository.id === repoId ? { ...r, isAnalyzing: true } : r
      )
    );
    try {
      await analyzeRepository(repoId);
      // Reload everything for this repository
      await loadRepositories(repoId);
      if (selectedRepoId === repoId) {
        await Promise.all([
          loadFiles(repoId),
          loadSymbols(repoId, selectedType, searchQuery),
          loadRelationships(repoId),
        ]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to analyze repository";
      setErrorMessage(msg);
    } finally {
      setReposStatus((prev) =>
        prev.map((r) =>
          r.repository.id === repoId ? { ...r, isAnalyzing: false } : r
        )
      );
    }
  }

  // Register new repository
  async function handleRegister(input: RepositoryCreateInput) {
    const created = await createRepository(input);
    await loadRepositories(created.id);
    setLeftTab("repos");
  }

  // Global Refresh
  async function handleRefreshAll() {
    setIsRefreshing(true);
    try {
      await pingHealth();
      await loadRepositories();
      if (selectedRepoId) {
        await Promise.all([
          loadFiles(selectedRepoId),
          loadSymbols(selectedRepoId, selectedType, searchQuery),
          loadRelationships(selectedRepoId),
          selectedSymbolId ? loadDetail(selectedRepoId, selectedSymbolId) : Promise.resolve(),
        ]);
      }
    } finally {
      setIsRefreshing(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-[#0b0f19] text-slate-100 overflow-hidden">
      {/* Top Navbar */}
      <Header
        backendHealthy={backendHealthy}
        repositories={reposStatus.map((r) => r.repository)}
        selectedRepoId={selectedRepoId}
        onSelectRepo={(id) => setSelectedRepoId(id)}
        onOpenRegisterModal={() => setIsRegisterModalOpen(true)}
        onRefresh={handleRefreshAll}
        isRefreshing={isRefreshing}
      />

      {/* Error Banner */}
      {errorMessage && (
        <div className="px-6 pt-3">
          <ErrorAlert
            message={errorMessage}
            onDismiss={() => setErrorMessage(null)}
            onRetry={handleRefreshAll}
          />
        </div>
      )}

      {/* Main 3-Column Dashboard Grid */}
      <main className="flex-1 overflow-hidden grid grid-cols-12 divide-x divide-slate-800">
        {/* Left Column: Repositories & File Explorer */}
        <section className="col-span-3 flex h-full flex-col bg-[#0f172a]/60">
          {/* Tabs */}
          <div className="flex border-b border-slate-800 bg-[#0f172a]/80 p-1.5">
            <button
              type="button"
              onClick={() => setLeftTab("explorer")}
              className={`flex-1 rounded-lg py-1.5 text-xs font-semibold transition ${
                leftTab === "explorer"
                  ? "bg-[#162032] text-sky-400 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              File Explorer
            </button>
            <button
              type="button"
              onClick={() => setLeftTab("repos")}
              className={`flex-1 rounded-lg py-1.5 text-xs font-semibold transition ${
                leftTab === "repos"
                  ? "bg-[#162032] text-sky-400 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Repositories ({reposStatus.length})
            </button>
          </div>

          {/* Active Repo Quick Banner */}
          {activeRepo && leftTab === "explorer" && (
            <div className="border-b border-slate-800/80 bg-[#162032]/40 px-3 py-2 flex items-center justify-between">
              <div className="min-w-0">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Active Codebase</span>
                <p className="truncate text-xs font-semibold text-white font-mono">{activeRepo.name}</p>
              </div>
              <button
                type="button"
                onClick={() => setLeftTab("repos")}
                className="text-[11px] text-sky-400 hover:underline"
              >
                Switch
              </button>
            </div>
          )}

          {/* Tab Content */}
          <div className="flex-1 overflow-hidden">
            {leftTab === "explorer" ? (
              <FileExplorer
                files={files}
                selectedFile={selectedFileFilter}
                onSelectFile={(f) => setSelectedFileFilter(f)}
                isLoading={isLoadingFiles}
              />
            ) : (
              <div className="h-full overflow-y-auto p-3">
                <RepositoryList
                  repositories={reposStatus}
                  selectedRepoId={selectedRepoId}
                  onSelectRepo={(id) => {
                    setSelectedRepoId(id);
                    setLeftTab("explorer");
                  }}
                  onAnalyzeRepo={handleAnalyze}
                  isLoading={isLoadingRepos}
                  onOpenRegisterModal={() => setIsRegisterModalOpen(true)}
                />
              </div>
            )}
          </div>
        </section>

        {/* Center Column: Searchable Symbols Explorer OR Interactive Call Graph */}
        <section className="col-span-5 flex h-full flex-col bg-[#0b0f19]">
          {/* View Mode Toggle Header */}
          <div className="flex items-center justify-between border-b border-slate-800 bg-[#0f172a]/90 px-4 py-2">
            <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-[#162032] p-0.5">
              <button
                type="button"
                id="btn-view-symbols"
                onClick={() => setCenterTab("symbols")}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
                  centerTab === "symbols"
                    ? "bg-sky-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Symbol Explorer ({symbols.length})
              </button>
              <button
                type="button"
                id="btn-view-graph"
                onClick={() => setCenterTab("graph")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition ${
                  centerTab === "graph"
                    ? "bg-sky-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <span>Call Graph</span>
                {callRelationships.length > 0 && (
                  <span className="rounded-full bg-slate-900/80 px-1.5 py-0.2 text-[10px] font-mono text-sky-300">
                    {callRelationships.length}
                  </span>
                )}
                {activeTrace && (
                  <span className="flex h-2 w-2 rounded-full bg-purple-400 ring-2 ring-purple-400/40" />
                )}
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setRightTab("trace")}
                className="flex items-center gap-1 text-[11px] font-medium text-purple-400 hover:text-purple-300 transition"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Trace Flow
              </button>
            </div>
          </div>

          {/* View Mode Content */}
          <div className="flex-1 overflow-hidden">
            {centerTab === "symbols" ? (
              <SymbolExplorer
                symbols={symbols}
                selectedSymbolId={selectedSymbolId}
                onSelectSymbol={handleSelectSymbol}
                searchQuery={searchQuery}
                onSearchChange={handleSearchChange}
                selectedType={selectedType}
                onTypeChange={handleTypeChange}
                selectedFileFilter={selectedFileFilter}
                onClearFileFilter={() => setSelectedFileFilter(null)}
                isLoading={isLoadingSymbols}
                isIndexed={isIndexed}
                onTriggerIndex={() => {
                  if (selectedRepoId) handleAnalyze(selectedRepoId);
                }}
              />
            ) : (
              <CallGraphView
                relationships={callRelationships}
                symbols={symbols}
                selectedSymbolId={selectedSymbolId}
                onSelectSymbol={handleSelectSymbol}
                isLoading={isLoadingRelationships}
                error={relationshipsError}
                onRetry={() => {
                  if (selectedRepoId) loadRelationships(selectedRepoId);
                }}
                isIndexed={isIndexed}
                onTriggerIndex={() => {
                  if (selectedRepoId) handleAnalyze(selectedRepoId);
                }}
                traceResult={activeTrace}
                onClearTrace={() => setActiveTrace(null)}
              />
            )}
          </div>
        </section>

        {/* Right Column: Symbol Detail Inspector OR Architecture Trace Panel */}
        <section className="col-span-4 flex h-full flex-col bg-[#0f172a]/30">
          {/* Tabs for Right Column */}
          <div className="flex border-b border-slate-800 bg-[#0f172a]/80 p-1.5">
            <button
              type="button"
              onClick={() => setRightTab("inspector")}
              className={`flex-1 rounded-lg py-1.5 text-xs font-semibold transition ${
                rightTab === "inspector"
                  ? "bg-[#162032] text-sky-400 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Symbol Inspector
            </button>
            <button
              type="button"
              onClick={() => setRightTab("trace")}
              className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold transition ${
                rightTab === "trace"
                  ? "bg-[#162032] text-purple-400 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <span>Architecture Trace</span>
              {activeTrace && (
                <span className="rounded-full bg-purple-950 px-1.5 py-0.2 text-[9px] font-mono font-bold text-purple-300 border border-purple-800/80">
                  {activeTrace.nodes.length}
                </span>
              )}
            </button>
          </div>

          {/* Right Column Content */}
          <div className="flex-1 overflow-hidden">
            {rightTab === "inspector" ? (
              <SymbolDetailView
                symbolDetail={symbolDetail}
                isLoading={isLoadingDetail}
                onNavigateToSymbol={handleNavigateToSymbol}
              />
            ) : (
              <ArchitectureTracePanel
                repositoryId={selectedRepoId}
                symbols={symbols}
                onTraceSuccess={handleTraceSuccess}
                onSelectTraceNode={handleSelectTraceNode}
                onClearTrace={() => setActiveTrace(null)}
                isTraceActive={activeTrace !== null}
              />
            )}
          </div>
        </section>
      </main>

      {/* Register Repository Modal */}
      <RegisterModal
        isOpen={isRegisterModalOpen}
        onClose={() => setIsRegisterModalOpen(false)}
        onSubmit={handleRegister}
      />
    </div>
  );
}

"use client";

import React from "react";
import { RepositoryStatus } from "@/types/api";

interface RepositoryListProps {
  repositories: RepositoryStatus[];
  selectedRepoId: number | null;
  onSelectRepo: (id: number) => void;
  onAnalyzeRepo: (id: number) => Promise<void>;
  isLoading: boolean;
  onOpenRegisterModal: () => void;
  isShowcaseMode?: boolean;
}

export function RepositoryList({
  repositories,
  selectedRepoId,
  onSelectRepo,
  onAnalyzeRepo,
  isLoading,
  onOpenRegisterModal,
  isShowcaseMode = false,
}: RepositoryListProps) {
  if (isLoading && repositories.length === 0) {
    return (
      <div className="space-y-3 p-4">
        <div className="h-4 w-28 bg-slate-800 rounded animate-pulse" />
        {[1, 2].map((i) => (
          <div key={i} className="h-20 rounded-xl bg-[#162032] border border-slate-800 animate-pulse" />
        ))}
      </div>
    );
  }

  if (repositories.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 bg-[#0f172a]/50 p-6 text-center">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-slate-400">
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
            />
          </svg>
        </div>
        <h3 className="mt-3 text-sm font-semibold text-slate-200">No repositories registered</h3>
        <p className="mt-1 text-xs text-slate-400">
          Register a local repository to explore its symbols, files, and AST call graph.
        </p>
        <button
          type="button"
          onClick={onOpenRegisterModal}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 transition"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Register Repository
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between px-1">
        <span className="text-xs font-semibold tracking-wide uppercase text-slate-400">
          Registered Repositories ({repositories.length})
        </span>
      </div>

      <div className="space-y-2">
        {repositories.map(({ repository, isIndexed, symbolCount, fileCount, isAnalyzing }) => {
          const isSelected = selectedRepoId === repository.id;

          return (
            <div
              key={repository.id}
              onClick={() => onSelectRepo(repository.id)}
              className={`group relative rounded-xl border p-3.5 transition cursor-pointer text-left ${
                isSelected
                  ? "border-sky-500/80 bg-[#162032] shadow-lg shadow-sky-500/5 ring-1 ring-sky-500/40"
                  : "border-slate-800 bg-[#111827]/70 hover:border-slate-700 hover:bg-[#162032]/80"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-white">
                      {repository.name}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">#{repository.id}</span>
                  </div>
                  <p
                    className="mt-1 truncate font-mono text-[11px] text-slate-400"
                    title={repository.path}
                  >
                    {repository.path}
                  </p>
                </div>

                {/* Indexed status badge */}
                <div>
                  {isAnalyzing ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-950/70 border border-amber-800/80 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                      <svg className="h-2.5 w-2.5 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                      </svg>
                      Indexing...
                    </span>
                  ) : isIndexed ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/70 border border-emerald-800/80 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      Indexed
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-400">
                      Not Indexed
                    </span>
                  )}
                </div>
              </div>

              {/* Stats & Actions */}
              <div className="mt-3 flex items-center justify-between border-t border-slate-800/80 pt-2 text-[11px] text-slate-400">
                <div className="flex items-center gap-3">
                  <span>
                    <strong className="text-slate-200">{fileCount}</strong> files
                  </span>
                  <span>•</span>
                  <span>
                    <strong className="text-slate-200">{symbolCount}</strong> symbols
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {isShowcaseMode ? (
                    <span
                      className="rounded border border-emerald-500/30 bg-emerald-950/40 px-2 py-0.5 text-[10px] font-medium text-emerald-300 select-none"
                      title="Precomputed static AST index snapshot (read-only showcase)"
                    >
                      Pre-indexed
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAnalyzeRepo(repository.id);
                      }}
                      disabled={isAnalyzing}
                      className="rounded border border-slate-700 bg-slate-800/80 px-2 py-0.5 text-[10px] font-medium text-slate-200 hover:border-sky-500 hover:text-white transition disabled:opacity-50"
                      title={isIndexed ? "Re-run AST analysis & indexing" : "Run AST analysis & index symbols"}
                    >
                      {isIndexed ? "Re-index" : "Index Now"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

"use client";

import React from "react";
import { Repository } from "@/types/api";

interface HeaderProps {
  backendHealthy: boolean | null;
  repositories: Repository[];
  selectedRepoId: number | null;
  onSelectRepo: (id: number) => void;
  onOpenRegisterModal: () => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export function Header({
  backendHealthy,
  repositories,
  selectedRepoId,
  onSelectRepo,
  onOpenRegisterModal,
  onRefresh,
  isRefreshing,
}: HeaderProps) {
  return (
    <header className="border-b border-slate-800 bg-[#0f172a]/95 backdrop-blur sticky top-0 z-30 px-6 py-3.5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-indigo-500 via-sky-500 to-emerald-400 p-0.5 shadow-lg shadow-indigo-500/20">
            <div className="flex h-full w-full items-center justify-center rounded-[7px] bg-[#0b0f19]">
              <span className="font-mono text-sm font-bold text-sky-400">&lt;/&gt;</span>
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-white">CodeLens AI</h1>
              <span className="rounded bg-indigo-950/80 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-800/60">
                Phase 3F.1
              </span>
            </div>
            <p className="text-xs text-slate-400">Codebase Intelligence & AST Explorer</p>
          </div>
        </div>

        {/* Center / Repository Selector & Health */}
        <div className="flex items-center gap-3">
          {/* Health status */}
          <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-[#162032] px-3 py-1 text-xs">
            <span
              className={`h-2 w-2 rounded-full ${
                backendHealthy === true
                  ? "bg-emerald-400 shadow-sm shadow-emerald-400/80"
                  : backendHealthy === false
                  ? "bg-rose-500 shadow-sm shadow-rose-500/80"
                  : "bg-amber-400 animate-pulse"
              }`}
            />
            <span className="text-slate-300">
              {backendHealthy === true
                ? "API Connected"
                : backendHealthy === false
                ? "API Offline"
                : "Checking API..."}
            </span>
          </div>

          {/* Repo selector dropdown */}
          {repositories.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Active Repo:</span>
              <select
                id="header-repo-select"
                value={selectedRepoId || ""}
                onChange={(e) => onSelectRepo(Number(e.target.value))}
                aria-label="Active repository selector"
                className="rounded-lg border border-slate-700 bg-[#162032] px-3 py-1.5 text-xs font-medium text-slate-200 outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
              >
                {repositories.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name} (ID: {repo.id})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            id="btn-refresh"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-[#162032] px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-[#1e293b] hover:text-white transition disabled:opacity-50"
            title="Refresh repository and symbol data"
          >
            <svg
              className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin text-sky-400" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            Refresh
          </button>

          <button
            type="button"
            id="btn-register-repo"
            onClick={onOpenRegisterModal}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-sky-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400 transition"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Register Repo
          </button>
        </div>
      </div>
    </header>
  );
}

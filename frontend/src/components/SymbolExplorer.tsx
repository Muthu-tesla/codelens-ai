"use client";

import React, { useMemo } from "react";
import { CodeSymbol, SymbolType } from "@/types/api";

interface SymbolExplorerProps {
  symbols: CodeSymbol[];
  selectedSymbolId: number | null;
  onSelectSymbol: (symbol: CodeSymbol) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  selectedType: string;
  onTypeChange: (type: string) => void;
  selectedFileFilter: string | null;
  onClearFileFilter: () => void;
  isLoading: boolean;
  isIndexed: boolean;
  onTriggerIndex: () => void;
}

const SYMBOL_TYPES = [
  { label: "All", value: "all" },
  { label: "Classes", value: "class" },
  { label: "Functions", value: "function" },
  { label: "Methods", value: "method" },
  { label: "Modules", value: "module" },
];

export function SymbolExplorer({
  symbols,
  selectedSymbolId,
  onSelectSymbol,
  searchQuery,
  onSearchChange,
  selectedType,
  onTypeChange,
  selectedFileFilter,
  onClearFileFilter,
  isLoading,
  isIndexed,
  onTriggerIndex,
}: SymbolExplorerProps) {
  // Client-side filtering by file if a file was selected in FileExplorer
  const filteredSymbols = useMemo(() => {
    let result = symbols;
    if (selectedFileFilter) {
      result = result.filter((s) => s.relative_path === selectedFileFilter);
    }
    return result;
  }, [symbols, selectedFileFilter]);

  function getBadgeColor(type: SymbolType): string {
    switch (type.toLowerCase()) {
      case "class":
        return "bg-indigo-950/80 text-indigo-300 border-indigo-700/60";
      case "function":
        return "bg-emerald-950/80 text-emerald-300 border-emerald-700/60";
      case "method":
        return "bg-amber-950/80 text-amber-300 border-amber-700/60";
      case "module":
        return "bg-sky-950/80 text-sky-300 border-sky-700/60";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  }

  function getBadgeLabel(type: SymbolType): string {
    switch (type.toLowerCase()) {
      case "class":
        return "class";
      case "function":
        return "def";
      case "method":
        return "method";
      case "module":
        return "mod";
      default:
        return type;
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Search & Filter Header */}
      <div className="border-b border-slate-800 p-4 space-y-3 bg-[#0f172a]/40">
        <div className="relative">
          <input
            id="symbol-search-input"
            type="text"
            placeholder="Search symbols by name or qualified path..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-[#162032] py-2 pl-9 pr-3 text-xs text-slate-100 placeholder-slate-400 outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
          />
          <svg
            className="absolute left-3 top-2.5 h-4 w-4 text-slate-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          {SYMBOL_TYPES.map((type) => {
            const isActive = selectedType === type.value;
            return (
              <button
                key={type.value}
                type="button"
                onClick={() => onTypeChange(type.value)}
                className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                  isActive
                    ? "bg-sky-600 text-white shadow-sm"
                    : "border border-slate-800 bg-[#162032] text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                {type.label}
              </button>
            );
          })}
        </div>

        {/* File Filter Pill if active */}
        {selectedFileFilter && (
          <div className="flex items-center justify-between rounded-lg bg-sky-950/40 border border-sky-800/60 px-2.5 py-1 text-xs text-sky-300">
            <span className="truncate text-[11px]">
              Filtered by: <strong className="font-mono text-sky-200">{selectedFileFilter}</strong>
            </span>
            <button
              type="button"
              onClick={onClearFileFilter}
              className="ml-2 text-sky-400 hover:text-white"
              title="Remove file filter"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* Symbols List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {isLoading ? (
          <div className="space-y-2 p-2">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="h-16 rounded-lg bg-[#162032]/60 border border-slate-800 animate-pulse"
              />
            ))}
          </div>
        ) : !isIndexed ? (
          <div className="p-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-slate-400">
              <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <h3 className="mt-3 text-sm font-semibold text-slate-200">Repository Not Yet Indexed</h3>
            <p className="mt-1 text-xs text-slate-400 max-w-xs mx-auto">
              Run AST analysis to extract code symbols, inheritance trees, and call relationships.
            </p>
            <button
              type="button"
              onClick={onTriggerIndex}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500 transition shadow-sm"
            >
              Run Indexing Now
            </button>
          </div>
        ) : filteredSymbols.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            No symbols found matching your criteria.
          </div>
        ) : (
          filteredSymbols.map((sym) => {
            const isSelected = selectedSymbolId === sym.id;

            return (
              <div
                key={sym.id}
                onClick={() => onSelectSymbol(sym)}
                className={`group rounded-lg border p-2.5 transition cursor-pointer text-left ${
                  isSelected
                    ? "border-sky-500 bg-sky-950/30 ring-1 ring-sky-500/30"
                    : "border-slate-800/80 bg-[#111827]/60 hover:border-slate-700 hover:bg-[#162032]/70"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`rounded border px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase ${getBadgeColor(
                        sym.symbol_type
                      )}`}
                    >
                      {getBadgeLabel(sym.symbol_type)}
                    </span>
                    <span className="truncate text-xs font-semibold text-slate-100 group-hover:text-sky-300">
                      {sym.name}
                    </span>
                  </div>

                  <span className="text-[10px] font-mono text-slate-400 shrink-0">
                    L{sym.line_start}–{sym.line_end}
                  </span>
                </div>

                <div className="mt-1 flex items-center justify-between gap-2 text-[11px]">
                  <p
                    className="truncate font-mono text-slate-400 text-[11px]"
                    title={sym.qualified_name}
                  >
                    {sym.qualified_name}
                  </p>
                </div>

                {sym.relative_path && (
                  <p
                    className="mt-0.5 truncate font-mono text-[10px] text-slate-400"
                    title={sym.relative_path}
                  >
                    {sym.relative_path}
                  </p>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer Count */}
      {isIndexed && (
        <div className="border-t border-slate-800 px-4 py-2 text-[11px] text-slate-500 bg-[#0f172a]/60">
          Showing <strong className="text-slate-300">{filteredSymbols.length}</strong> symbols
          {selectedFileFilter ? " in selected file" : ""}
        </div>
      )}
    </div>
  );
}

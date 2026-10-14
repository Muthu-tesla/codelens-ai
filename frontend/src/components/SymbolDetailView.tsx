"use client";

import React from "react";
import { CodeSymbolDetail, SymbolType } from "@/types/api";

interface SymbolDetailViewProps {
  symbolDetail: CodeSymbolDetail | null;
  isLoading: boolean;
  onNavigateToSymbol?: (symbolId: number) => void;
}

export function SymbolDetailView({
  symbolDetail,
  isLoading,
  onNavigateToSymbol,
}: SymbolDetailViewProps) {
  if (isLoading) {
    return (
      <div className="h-full p-6 space-y-4">
        <div className="h-6 w-1/3 bg-slate-800 rounded animate-pulse" />
        <div className="h-4 w-2/3 bg-slate-800/60 rounded animate-pulse" />
        <div className="h-28 bg-[#162032] rounded-xl border border-slate-800 animate-pulse" />
        <div className="h-36 bg-[#162032] rounded-xl border border-slate-800 animate-pulse" />
      </div>
    );
  }

  if (!symbolDetail) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center text-slate-500">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#162032] border border-slate-800 text-slate-400">
          <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
            />
          </svg>
        </div>
        <h3 className="mt-4 text-sm font-semibold text-slate-300">No Symbol Selected</h3>
        <p className="mt-1 max-w-xs text-xs text-slate-400">
          Select any symbol from the explorer to inspect its full signature, docstring, source location, and AST relationships.
        </p>
      </div>
    );
  }

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

  function getRelTypeBadge(type: string): string {
    switch (type.toLowerCase()) {
      case "calls":
        return "bg-amber-950/70 text-amber-300 border-amber-800/80";
      case "contains":
        return "bg-sky-950/70 text-sky-300 border-sky-800/80";
      case "inherits":
        return "bg-purple-950/70 text-purple-300 border-purple-800/80";
      case "imports":
        return "bg-slate-800 text-slate-300 border-slate-700";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* Header Info */}
      <div className="border-b border-slate-800 pb-5">
        <div className="flex items-center gap-2.5">
          <span
            className={`rounded border px-2 py-0.5 text-xs font-mono font-semibold uppercase ${getBadgeColor(
              symbolDetail.symbol_type
            )}`}
          >
            {symbolDetail.symbol_type}
          </span>
          <h2 className="text-xl font-bold tracking-tight text-white">{symbolDetail.name}</h2>
        </div>

        <div className="mt-2.5">
          <p className="font-mono text-xs text-sky-400 select-all break-all">
            {symbolDetail.qualified_name}
          </p>
        </div>

        {/* Source Location */}
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <div className="flex items-center gap-1.5 font-mono">
            <svg className="h-3.5 w-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span className="text-slate-300">{symbolDetail.relative_path}</span>
          </div>

          <span className="text-slate-600">•</span>

          <div className="flex items-center gap-1 font-mono text-slate-300">
            <span>Lines {symbolDetail.line_start} – {symbolDetail.line_end}</span>
            <span className="text-slate-500">({symbolDetail.line_end - symbolDetail.line_start + 1} lines)</span>
          </div>
        </div>
      </div>

      {/* Signature Section */}
      {symbolDetail.signature && (
        <div className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Signature
          </span>
          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#0b0f19] p-3.5">
            <pre className="font-mono text-xs text-emerald-300 whitespace-pre-wrap">
              {symbolDetail.signature}
            </pre>
          </div>
        </div>
      )}

      {/* Docstring Section */}
      <div className="space-y-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Documentation / Docstring
        </span>
        {symbolDetail.docstring ? (
          <div className="rounded-xl border border-slate-800 bg-[#162032]/80 p-4">
            <pre className="font-sans text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">
              {symbolDetail.docstring}
            </pre>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800/60 bg-[#162032]/30 p-3 text-xs italic text-slate-500">
            No docstring provided for this symbol.
          </div>
        )}
      </div>

      {/* Outgoing Relationships */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Outgoing Relationships ({symbolDetail.outgoing_relationships.length})
          </span>
        </div>

        {symbolDetail.outgoing_relationships.length === 0 ? (
          <p className="text-xs text-slate-500 italic">No outgoing relationships found.</p>
        ) : (
          <div className="space-y-1.5">
            {symbolDetail.outgoing_relationships.map((rel) => (
              <div
                key={rel.id}
                className="flex items-center justify-between rounded-lg border border-slate-800/80 bg-[#111827]/60 px-3 py-2 text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase font-semibold ${getRelTypeBadge(
                      rel.relationship_type
                    )}`}
                  >
                    {rel.relationship_type}
                  </span>
                  <button
                    type="button"
                    onClick={() => onNavigateToSymbol?.(rel.target_symbol.id)}
                    className="truncate font-mono text-xs text-sky-400 hover:underline hover:text-sky-300 text-left"
                    title={rel.target_symbol.qualified_name}
                  >
                    {rel.target_symbol.qualified_name}
                  </button>
                </div>
                {rel.source_line && (
                  <span className="font-mono text-[10px] text-slate-500 shrink-0 ml-2">
                    Line {rel.source_line}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Incoming Relationships */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Incoming Relationships ({symbolDetail.incoming_relationships.length})
          </span>
        </div>

        {symbolDetail.incoming_relationships.length === 0 ? (
          <p className="text-xs text-slate-500 italic">No incoming relationships found.</p>
        ) : (
          <div className="space-y-1.5">
            {symbolDetail.incoming_relationships.map((rel) => (
              <div
                key={rel.id}
                className="flex items-center justify-between rounded-lg border border-slate-800/80 bg-[#111827]/60 px-3 py-2 text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase font-semibold ${getRelTypeBadge(
                      rel.relationship_type
                    )}`}
                  >
                    {rel.relationship_type}
                  </span>
                  <button
                    type="button"
                    onClick={() => onNavigateToSymbol?.(rel.source_symbol.id)}
                    className="truncate font-mono text-xs text-sky-400 hover:underline hover:text-sky-300 text-left"
                    title={rel.source_symbol.qualified_name}
                  >
                    {rel.source_symbol.qualified_name}
                  </button>
                </div>
                {rel.source_line && (
                  <span className="font-mono text-[10px] text-slate-500 shrink-0 ml-2">
                    Line {rel.source_line}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

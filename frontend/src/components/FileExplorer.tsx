"use client";

import React, { useMemo, useState } from "react";
import { FileMetadata } from "@/types/api";

interface FileExplorerProps {
  files: FileMetadata[];
  selectedFile: string | null;
  onSelectFile: (filePath: string | null) => void;
  isLoading: boolean;
}

export function FileExplorer({
  files,
  selectedFile,
  onSelectFile,
  isLoading,
}: FileExplorerProps) {
  const [filterQuery, setFilterQuery] = useState("");

  const filteredFiles = useMemo(() => {
    if (!filterQuery.trim()) return files;
    const q = filterQuery.toLowerCase();
    return files.filter(
      (f) =>
        f.relative_path.toLowerCase().includes(q) ||
        f.extension.toLowerCase().includes(q)
    );
  }, [files, filterQuery]);

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header & Search */}
      <div className="border-b border-slate-800 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Files ({files.length})
          </span>
          {selectedFile && (
            <button
              type="button"
              onClick={() => onSelectFile(null)}
              className="text-[11px] text-sky-400 hover:text-sky-300 underline"
            >
              Clear filter
            </button>
          )}
        </div>

        <div className="relative">
          <input
            type="text"
            placeholder="Filter files..."
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            className="w-full rounded-lg border border-slate-800 bg-[#162032] py-1.5 pl-8 pr-3 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
          />
          <svg
            className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-500"
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
      </div>

      {/* Files List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading ? (
          <div className="space-y-2 p-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-8 rounded bg-slate-800/60 animate-pulse" />
            ))}
          </div>
        ) : files.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-500">
            No source files discovered.
          </div>
        ) : filteredFiles.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-500">
            No files match &quot;{filterQuery}&quot;.
          </div>
        ) : (
          filteredFiles.map((file) => {
            const isSelected = selectedFile === file.relative_path;
            const isPython = file.extension === ".py";

            return (
              <button
                key={file.relative_path}
                type="button"
                onClick={() =>
                  onSelectFile(isSelected ? null : file.relative_path)
                }
                className={`w-full flex items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition ${
                  isSelected
                    ? "bg-sky-600/20 text-sky-300 font-medium border border-sky-500/40"
                    : "text-slate-300 hover:bg-[#162032] hover:text-white"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`rounded px-1 py-0.2 text-[9px] font-mono uppercase font-semibold ${
                      isPython
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-800/60"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {file.extension.replace(".", "")}
                  </span>
                  <span className="truncate font-mono text-[11px]" title={file.relative_path}>
                    {file.relative_path}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-[10px] text-slate-500 shrink-0 ml-2">
                  <span>{file.line_count} L</span>
                  <span>{formatBytes(file.size_bytes)}</span>
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

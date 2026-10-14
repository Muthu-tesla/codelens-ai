"use client";

import React, { useState } from "react";
import { RepositoryCreateInput } from "@/types/api";

interface RegisterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: RepositoryCreateInput) => Promise<void>;
}

export function RegisterModal({ isOpen, onClose, onSubmit }: RegisterModalProps) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("evaluation_repos/tinydb");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !path.trim()) {
      setError("Please provide both a repository name and a local directory path.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await onSubmit({ name: name.trim(), path: path.trim() });
      setName("");
      setPath("evaluation_repos/tinydb");
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to register repository.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div
        className="w-full max-w-md rounded-2xl border border-slate-700 bg-[#0f172a] p-6 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h2 id="modal-title" className="text-base font-semibold text-white">
              Register Local Repository
            </h2>
            <p className="text-xs text-slate-400">
              Link a local codebase to run AST analysis and symbol extraction.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {error && (
            <div className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-3 text-xs text-rose-300">
              <p className="font-medium">Registration Failed</p>
              <p className="mt-0.5 text-rose-400">{error}</p>
            </div>
          )}

          <div>
            <label htmlFor="repo-name" className="block text-xs font-medium text-slate-300 mb-1">
              Repository Name
            </label>
            <input
              id="repo-name"
              type="text"
              placeholder="e.g. tinydb"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-[#162032] px-3 py-2 text-sm text-slate-200 placeholder-slate-500 outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
              required
            />
          </div>

          <div>
            <label htmlFor="repo-path" className="block text-xs font-medium text-slate-300 mb-1">
              Local Directory Path
            </label>
            <input
              id="repo-path"
              type="text"
              placeholder="e.g. evaluation_repos/tinydb"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-[#162032] px-3 py-2 text-sm text-slate-200 placeholder-slate-500 outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 font-mono text-xs"
              required
            />
            <p className="mt-1 text-[11px] text-slate-500">
              Can be an absolute path or relative to project root (e.g., <code className="text-slate-400">evaluation_repos/tinydb</code>).
            </p>
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="rounded-lg border border-slate-700 bg-transparent px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              id="btn-submit-register"
              disabled={isSubmitting}
              className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50 shadow-sm"
            >
              {isSubmitting ? (
                <>
                  <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                    />
                  </svg>
                  Registering...
                </>
              ) : (
                "Register Repository"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

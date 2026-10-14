"use client";

import React from "react";

interface ErrorAlertProps {
  message: string | null;
  onDismiss: () => void;
  onRetry?: () => void;
}

export function ErrorAlert({ message, onDismiss, onRetry }: ErrorAlertProps) {
  if (!message) return null;

  return (
    <div className="flex items-center justify-between rounded-xl border border-rose-900/80 bg-rose-950/50 p-4 text-xs text-rose-200 shadow-lg">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-rose-900/60 p-1.5 text-rose-300">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <div>
          <p className="font-semibold text-rose-100">API Error Occurred</p>
          <p className="mt-0.5 text-rose-300/90">{message}</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg bg-rose-900/70 px-2.5 py-1 text-xs font-medium text-rose-200 hover:bg-rose-800 transition"
          >
            Retry
          </button>
        )}
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-lg p-1 text-rose-400 hover:bg-rose-900/40 hover:text-white"
          title="Dismiss error"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

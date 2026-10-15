"use client";

import React, { useState } from "react";
import {
  ArchitectureExplainResponse,
  ArchitectureTraceEdge,
  ArchitectureTraceNode,
  ArchitectureTraceResponse,
  CodeSymbol,
  EvidenceItem,
} from "@/types/api";
import { ApiError, explainArchitecture, traceArchitecture } from "@/lib/api";
import {
  getShowcaseBenchmarkQueries,
  getShowcaseExplain,
  getShowcaseTrace,
} from "@/lib/showcase-adapter";

interface ArchitectureTracePanelProps {
  repositoryId: number | null;
  symbols: CodeSymbol[];
  onTraceSuccess: (trace: {
    nodes: ArchitectureTraceNode[];
    edges: ArchitectureTraceEdge[];
    startSymbol: string;
  }) => void;
  onSelectTraceNode: (node: ArchitectureTraceNode) => void;
  onClearTrace: () => void;
  isTraceActive: boolean;
  isShowcaseMode?: boolean;
}

const EXAMPLE_QUESTIONS = [
  "How does table insertion persist a document?",
  "How does search query table documents?",
  "How does table remove delete records?",
];

export function ArchitectureTracePanel({
  repositoryId,
  symbols,
  onTraceSuccess,
  onSelectTraceNode,
  onClearTrace,
  isTraceActive,
  isShowcaseMode = false,
}: ArchitectureTracePanelProps) {
  const [mode, setMode] = useState<"question" | "symbol">("question");
  const [question, setQuestion] = useState("How does table insertion persist a document?");
  const [selectedStartSymbol, setSelectedStartSymbol] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unsupportedNotice, setUnsupportedNotice] = useState<string | null>(null);

  // Result state
  const [explainResult, setExplainResult] = useState<ArchitectureExplainResponse | null>(null);
  const [traceResult, setTraceResult] = useState<ArchitectureTraceResponse | null>(null);
  const [activeEvidence, setActiveEvidence] = useState<EvidenceItem | null>(null);

  // Callable symbols for the start symbol dropdown
  const callableSymbols = symbols.filter((s) =>
    ["function", "method"].includes(s.symbol_type.toLowerCase())
  );

  const benchmarkQueries = isShowcaseMode ? getShowcaseBenchmarkQueries() : [];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!repositoryId) return;

    setIsLoading(true);
    setError(null);
    setUnsupportedNotice(null);
    setExplainResult(null);
    setTraceResult(null);

    try {
      if (mode === "question") {
        const cleanQ = question.trim();
        if (!cleanQ) {
          setError("Please enter a question.");
          setIsLoading(false);
          return;
        }

        if (isShowcaseMode) {
          const res = await getShowcaseExplain(repositoryId, cleanQ);
          setExplainResult(res);

          if (!res.trace || res.answer.includes("couldn't determine this confidently")) {
            setUnsupportedNotice(
              "Out-of-benchmark query or ungrounded concept. In ₹0 static showcase mode, questions are evaluated against verified TinyDB benchmark test cases without running a live LLM."
            );
          } else {
            onTraceSuccess({
              nodes: res.trace.nodes,
              edges: res.trace.edges,
              startSymbol: res.trace.start_symbol,
            });
          }
        } else {
          try {
            const res = await explainArchitecture(repositoryId, cleanQ);
            setExplainResult(res);

            if (!res.trace || res.answer.includes("couldn't determine this confidently")) {
              setUnsupportedNotice(
                "No confident start symbol could be resolved from this question in the repository. Try rephrasing or use Deterministic Trace with a specific start symbol."
              );
            } else {
              onTraceSuccess({
                nodes: res.trace.nodes,
                edges: res.trace.edges,
                startSymbol: res.trace.start_symbol,
              });
            }
          } catch (err: unknown) {
            // If LLM is not configured (HTTP 503), offer graceful deterministic fallback
            const is503 =
              (err instanceof ApiError && err.status === 503) ||
              (err instanceof Error && err.message.includes("LLM service is not configured")) ||
              (typeof err === "object" && err !== null && "status" in err && (err as { status: unknown }).status === 503);
            if (is503) {
              setError(
                "LLM service is not configured (OPENAI_API_KEY not set). You can switch to Deterministic Trace tab to trace execution without requiring an LLM."
              );
            } else {
              throw err;
            }
          }
        }
      } else {
        // Direct symbol trace
        const targetSym = selectedStartSymbol.trim();
        if (!targetSym) {
          setError("Please select or enter a start symbol.");
          setIsLoading(false);
          return;
        }

        if (isShowcaseMode) {
          const res = await getShowcaseTrace(repositoryId, targetSym);
          setTraceResult(res);
          onTraceSuccess({
            nodes: res.nodes,
            edges: res.edges,
            startSymbol: res.start_symbol,
          });
        } else {
          const res = await traceArchitecture(repositoryId, targetSym);
          setTraceResult(res);
          onTraceSuccess({
            nodes: res.nodes,
            edges: res.edges,
            startSymbol: res.start_symbol,
          });
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Architecture trace request failed.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }

  function handleReset() {
    setExplainResult(null);
    setTraceResult(null);
    setError(null);
    setUnsupportedNotice(null);
    setActiveEvidence(null);
    onClearTrace();
  }

  const activeNodes = explainResult?.trace?.nodes || traceResult?.nodes || [];
  const activeEdges = explainResult?.trace?.edges || traceResult?.edges || [];
  const activeStartSymbol = explainResult?.trace?.start_symbol || traceResult?.start_symbol;

  return (
    <div className="flex h-full flex-col overflow-y-auto p-4 space-y-4 bg-[#0f172a]/30">
      {/* Panel Header */}
      <div className="border-b border-slate-800 pb-3 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-purple-400" />
            <h3 className="text-sm font-bold text-white">Architecture Intelligence Trace</h3>
            {isShowcaseMode && (
              <span className="rounded border border-purple-500/40 bg-purple-950/60 px-1.5 py-0.5 text-[9px] font-semibold text-purple-300">
                ₹0 Showcase
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-slate-400">
            {isShowcaseMode
              ? "Explore precomputed static AST call flows & grounded source evidence from verified TinyDB benchmarks."
              : "Infer static call flows and grounded evidence citations from codebase questions."}
          </p>
        </div>

        {isTraceActive && (
          <button
            type="button"
            onClick={handleReset}
            className="rounded border border-purple-800/80 bg-purple-950/60 px-2 py-1 text-[10px] font-semibold text-purple-200 hover:bg-purple-900/80 transition"
          >
            Reset Trace
          </button>
        )}
      </div>

      {/* Mode Switcher */}
      <div className="flex rounded-lg border border-slate-800 bg-[#162032] p-0.5">
        <button
          type="button"
          onClick={() => {
            setMode("question");
            setError(null);
          }}
          className={`flex-1 rounded py-1 text-xs font-semibold transition ${
            mode === "question"
              ? "bg-purple-600 text-white shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Ask Question (Explain)
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("symbol");
            setError(null);
          }}
          className={`flex-1 rounded py-1 text-xs font-semibold transition ${
            mode === "symbol"
              ? "bg-purple-600 text-white shadow-sm"
              : "text-slate-400 hover:text-white"
          }`}
        >
          Start Symbol (Trace)
        </button>
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        {mode === "question" ? (
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Codebase Architecture Question
            </label>
            <textarea
              rows={2}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. How does table insertion persist a document?"
              className="w-full rounded-lg border border-slate-700 bg-[#162032] p-2.5 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 resize-none font-sans"
              required
            />

            {/* Example Queries */}
            {isShowcaseMode ? (
              <div className="mt-2 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold text-purple-300">
                    Precomputed Benchmark Examples (Offline):
                  </span>
                  <span className="text-[9px] text-slate-500 font-mono">10 flows • 3 negative tests</span>
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto pr-1">
                  {benchmarkQueries.map((bq) => (
                    <button
                      key={bq.id}
                      type="button"
                      onClick={() => setQuestion(bq.question)}
                      className={`rounded border px-2 py-0.5 text-[10px] transition truncate max-w-full text-left ${
                        question === bq.question
                          ? "border-purple-500 bg-purple-950/70 text-purple-200"
                          : bq.is_negative
                          ? "border-amber-900/50 bg-[#151119] text-amber-300/80 hover:border-amber-700 hover:text-amber-200"
                          : "border-slate-800 bg-[#111827] text-slate-400 hover:border-purple-600 hover:text-purple-300"
                      }`}
                      title={bq.is_negative ? `[Negative Refusal Test] ${bq.question}` : `[${bq.category}] ${bq.question}`}
                    >
                      <span className="font-mono text-[9px] opacity-70 mr-1">[{bq.id}]</span>
                      {bq.question}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-[10px] text-slate-500">Examples:</span>
                {EXAMPLE_QUESTIONS.map((eq) => (
                  <button
                    key={eq}
                    type="button"
                    onClick={() => setQuestion(eq)}
                    className="rounded border border-slate-800 bg-[#111827] px-2 py-0.5 text-[10px] text-slate-400 hover:border-purple-600 hover:text-purple-300 transition truncate max-w-full"
                  >
                    {eq}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Select Start Symbol
            </label>
            <select
              value={selectedStartSymbol}
              onChange={(e) => setSelectedStartSymbol(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-[#162032] p-2 text-xs text-slate-200 outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 font-mono"
              required
            >
              <option value="">-- Choose a function or method --</option>
              {callableSymbols.map((s) => (
                <option key={s.id} value={s.qualified_name}>
                  {s.qualified_name}
                </option>
              ))}
            </select>
          </div>
        )}

        <button
          type="submit"
          disabled={isLoading || !repositoryId}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 py-2 text-xs font-semibold text-white hover:bg-purple-500 disabled:opacity-50 transition shadow-sm"
        >
          {isLoading ? (
            <>
              <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              Tracing Architecture Flow...
            </>
          ) : (
            <>
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Trace Architecture Flow
            </>
          )}
        </button>
      </form>

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-rose-900/80 bg-rose-950/40 p-3 text-xs text-rose-300">
          <p className="font-semibold text-rose-200">Error</p>
          <p className="mt-0.5">{error}</p>
        </div>
      )}

      {/* Unsupported question / Safe fallback */}
      {unsupportedNotice && (
        <div className="rounded-lg border border-amber-900/80 bg-amber-950/40 p-3 text-xs text-amber-200">
          <div className="flex items-center gap-1.5 font-semibold text-amber-300">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            Out-of-Domain or Ambiguous Query
          </div>
          <p className="mt-1 text-amber-200/90">{unsupportedNotice}</p>
        </div>
      )}

      {/* AI Grounded Explanation */}
      {explainResult && explainResult.answer && (
        <div className="rounded-xl border border-purple-900/60 bg-[#162032]/80 p-3.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-purple-300">
              {isShowcaseMode ? "Precomputed Grounded Architecture Explanation" : "Grounded Architecture Explanation"}
            </span>
            <span className="rounded bg-purple-950 px-1.5 py-0.5 text-[9px] font-semibold text-purple-300 border border-purple-800/60">
              {isShowcaseMode ? "Precomputed Snapshot" : "AI Grounded"}
            </span>
          </div>

          <div className="text-xs text-slate-200 leading-relaxed font-sans whitespace-pre-wrap">
            {explainResult.answer}
          </div>
        </div>
      )}

      {/* Deterministic Summary (if direct trace mode) */}
      {traceResult && (
        <div className="rounded-xl border border-purple-900/60 bg-[#162032]/80 p-3.5 space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-purple-300">
              {isShowcaseMode ? "Precomputed Static AST Summary" : "Deterministic Trace Summary"}
            </span>
            {isShowcaseMode && (
              <span className="rounded bg-purple-950 px-1.5 py-0.5 text-[9px] font-semibold text-purple-300 border border-purple-800/60">
                Static AST
              </span>
            )}
          </div>
          <p className="text-xs text-slate-300 font-sans leading-relaxed">
            {traceResult.summary}
          </p>
        </div>
      )}

      {/* Traced Call Flow Sequence */}
      {activeNodes.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              {isShowcaseMode ? "Static AST Call Flow" : "Inferred Call Flow"} ({activeNodes.length} steps)
            </span>
            <span className="text-[10px] text-purple-400 font-mono">
              Start: {activeStartSymbol}
            </span>
          </div>

          <div className="space-y-1.5">
            {activeNodes.map((node) => {
              const isStart = node.step === 1 || node.qualified_name === activeStartSymbol;
              const incomingEdge = activeEdges.find(
                (e) => (e.to || e.to_symbol) === node.qualified_name
              );
              const callerQName = incomingEdge ? (incomingEdge.from || incomingEdge.from_symbol) : null;
              const callerShort = callerQName ? callerQName.split(".").pop() : null;

              return (
                <div
                  key={node.step}
                  onClick={() => onSelectTraceNode(node)}
                  className={`group flex items-center justify-between rounded-lg border p-2 transition cursor-pointer text-left ${
                    isStart
                      ? "border-purple-500/80 bg-purple-950/40 hover:bg-purple-900/50"
                      : "border-slate-800 bg-[#111827]/70 hover:border-slate-700 hover:bg-[#162032]"
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-mono font-bold ${
                        isStart
                          ? "bg-purple-500 text-white"
                          : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      {node.step}
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <p className="truncate font-mono text-xs font-semibold text-slate-200 group-hover:text-purple-300">
                          {node.name}
                        </p>
                        {isStart ? (
                          <span className="rounded bg-purple-900/60 border border-purple-700/60 px-1 py-0.2 text-[9px] font-mono text-purple-300 font-medium">
                            Entry Point
                          </span>
                        ) : callerShort ? (
                          <span
                            className="truncate rounded bg-slate-800/80 border border-slate-700/60 px-1 py-0.2 text-[9px] font-mono text-slate-300"
                            title={`Called by ${callerQName}${incomingEdge?.source_line ? ` at line ${incomingEdge.source_line}` : ""}`}
                          >
                            ↳ called by <strong className="text-purple-300">{callerShort}</strong>
                            {incomingEdge?.source_line ? ` (L${incomingEdge.source_line})` : ""}
                          </span>
                        ) : null}
                      </div>
                      <p className="truncate font-mono text-[10px] text-slate-400" title={node.qualified_name}>
                        {node.qualified_name}
                      </p>
                    </div>
                  </div>

                  <div className="text-right shrink-0 ml-2">
                    <span className="rounded px-1 py-0.2 text-[9px] font-mono uppercase bg-slate-800 text-slate-400">
                      {node.symbol_type}
                    </span>
                    {node.line_start && (
                      <p className="mt-0.5 text-[9px] font-mono text-slate-500">
                        L{node.line_start}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Grounded Evidence Citations */}
      {explainResult && explainResult.evidence.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Source Evidence Citations ({explainResult.evidence.length})
          </span>

          <div className="space-y-2">
            {explainResult.evidence.map((ev) => {
              const isSelected = activeEvidence?.id === ev.id;

              return (
                <div
                  key={ev.id}
                  onClick={() => setActiveEvidence(isSelected ? null : ev)}
                  className={`rounded-lg border p-2.5 transition cursor-pointer text-xs ${
                    isSelected
                      ? "border-sky-500/80 bg-[#162032]"
                      : "border-slate-800/80 bg-[#111827]/60 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-sky-950 border border-sky-800/80 px-1.5 py-0.2 font-mono text-[10px] font-bold text-sky-300">
                        [{ev.id}]
                      </span>
                      <span className="font-mono text-[11px] text-slate-200 truncate">
                        {ev.file}
                      </span>
                    </div>
                    {ev.line_start && ev.line_end && (
                      <span className="font-mono text-[10px] text-slate-500">
                        L{ev.line_start}–{ev.line_end}
                      </span>
                    )}
                  </div>

                  {/* Expandable snippet content */}
                  {isSelected && (
                    <div className="mt-2 overflow-x-auto rounded border border-slate-800 bg-[#0b0f19] p-2">
                      <pre className="font-mono text-[10px] text-emerald-300 whitespace-pre-wrap">
                        {ev.content}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Static Inference Disclaimer */}
      <div className="rounded-lg border border-purple-900/40 bg-[#0f172a]/80 p-2.5 text-[10px] text-slate-400 leading-normal space-y-1">
        <p>
          <strong className="text-purple-300">Static AST Analysis Notice:</strong> Reconstructed statically from AST <code className="text-purple-300">CALLS</code> graph relationships. Represents code structure rather than dynamic runtime execution.
        </p>
        {isShowcaseMode && (
          <p className="text-slate-500">
            Operating in ₹0 Static Showcase Mode. Results are precomputed from verified TinyDB AST analysis; no live backend, embeddings, or LLM tokens are consumed.
          </p>
        )}
      </div>
    </div>
  );
}

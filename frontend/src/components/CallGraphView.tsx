"use client";

import React, { useMemo, useState, useCallback, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  ArchitectureTraceEdge,
  ArchitectureTraceNode,
  CodeRelationship,
  CodeSymbol,
} from "@/types/api";
import { extractCallSubgraph, CallGraphNode as CallGraphNodeData } from "@/lib/graph-utils";
import { CallGraphNodeComponent } from "./CallGraphNode";

interface CallGraphViewProps {
  relationships: CodeRelationship[];
  symbols: CodeSymbol[];
  selectedSymbolId: number | null;
  onSelectSymbol: (symbol: CodeSymbol) => void;
  isLoading: boolean;
  error: string | null;
  onRetry?: () => void;
  isIndexed: boolean;
  onTriggerIndex: () => void;
  traceResult?: {
    nodes: ArchitectureTraceNode[];
    edges: ArchitectureTraceEdge[];
    startSymbol?: string;
  } | null;
  onClearTrace?: () => void;
}

const nodeTypes: NodeTypes = {
  callNode: CallGraphNodeComponent,
};

export function CallGraphView({
  relationships,
  symbols,
  selectedSymbolId,
  onSelectSymbol,
  isLoading,
  error,
  onRetry,
  isIndexed,
  onTriggerIndex,
  traceResult,
  onClearTrace,
}: CallGraphViewProps) {
  // Graph configuration state
  const [depth, setDepth] = useState<number>(1);
  const [maxNodes, setMaxNodes] = useState<number>(25);
  const [searchFilter, setSearchFilter] = useState<string>("");
  const [prevSelectedSymbolId, setPrevSelectedSymbolId] = useState<number | null>(selectedSymbolId);
  const [focusedId, setFocusedId] = useState<number | null>(selectedSymbolId);

  // Sync focusedId when selectedSymbolId changes externally (e.g. from file explorer or list)
  if (selectedSymbolId !== prevSelectedSymbolId) {
    setPrevSelectedSymbolId(selectedSymbolId);
    if (selectedSymbolId !== null) {
      setFocusedId(selectedSymbolId);
    }
  }

  // Compute subgraph based on focus, depth, maxNodes, and active trace
  const subgraph = useMemo(() => {
    return extractCallSubgraph(relationships, symbols, {
      focusedSymbolId: focusedId,
      depth,
      maxNodes,
      traceNodes: traceResult?.nodes,
      traceEdges: traceResult?.edges,
      traceStartSymbol: traceResult?.startSymbol,
    });
  }, [relationships, symbols, focusedId, depth, maxNodes, traceResult]);

  // Map subgraph nodes to React Flow Node structure
  const flowNodes: Node<CallGraphNodeData>[] = useMemo(() => {
    return subgraph.nodes.map((n) => ({
      id: n.id,
      type: "callNode",
      position: n.position,
      data: n,
      selected: n.symbolId === (focusedId ?? subgraph.focusedSymbolId),
    }));
  }, [subgraph.nodes, focusedId, subgraph.focusedSymbolId]);

  // Map subgraph edges to React Flow Edge structure
  const flowEdges: Edge[] = useMemo(() => {
    return subgraph.edges.map((e) => {
      const isTraceEdge = e.isTraceEdge;
      const isHighlighted = e.isHighlighted;
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        animated: isTraceEdge || isHighlighted,
        style: {
          stroke: isTraceEdge ? "#c084fc" : isHighlighted ? "#38bdf8" : "#475569",
          strokeWidth: isTraceEdge ? 3 : isHighlighted ? 2.5 : 1.5,
          opacity: isTraceEdge ? 1 : isHighlighted ? 1 : 0.6,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: isTraceEdge ? "#c084fc" : isHighlighted ? "#38bdf8" : "#64748b",
        },
        label: e.sourceLine ? `L${e.sourceLine}` : undefined,
        labelStyle: {
          fill: isTraceEdge ? "#e9d5ff" : "#94a3b8",
          fontSize: 10,
          fontFamily: "monospace",
          fontWeight: isTraceEdge ? "bold" : "normal",
        },
        labelBgStyle: { fill: "#0f172a", fillOpacity: 0.8 },
      };
    });
  }, [subgraph.edges]);

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  // Update nodes and edges whenever subgraph updates
  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [flowNodes, flowEdges, setNodes, setEdges]);

  // Handle node selection
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const symId = Number(node.id);
      setFocusedId(symId);
      const matched = symbols.find((s) => s.id === symId);
      if (matched) {
        onSelectSymbol(matched);
      }
    },
    [symbols, onSelectSymbol]
  );

  // Filter callable functions for the focus dropdown/search
  const callableSymbols = useMemo(() => {
    const list = symbols.filter((s) =>
      ["function", "method"].includes(s.symbol_type.toLowerCase())
    );
    if (!searchFilter.trim()) return list.slice(0, 50);
    const q = searchFilter.toLowerCase();
    return list
      .filter((s) => s.name.toLowerCase().includes(q) || s.qualified_name.toLowerCase().includes(q))
      .slice(0, 50);
  }, [symbols, searchFilter]);

  // 1. Loading state
  if (isLoading && relationships.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-[#0b0f19]">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#162032] border border-slate-800 text-sky-400">
          <svg className="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        </div>
        <h3 className="mt-4 text-sm font-semibold text-slate-200">Loading Call Graph</h3>
        <p className="mt-1 text-xs text-slate-400">
          Fetching AST relationships and constructing function call flow...
        </p>
      </div>
    );
  }

  // 2. Error state
  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-[#0b0f19]">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-950/60 border border-rose-800 text-rose-400">
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h3 className="mt-4 text-sm font-semibold text-rose-200">Failed to Load Graph Data</h3>
        <p className="mt-1 text-xs text-rose-400 max-w-sm">{error}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 rounded-lg bg-rose-900/80 px-4 py-1.5 text-xs font-medium text-rose-100 hover:bg-rose-800 transition"
          >
            Retry Loading
          </button>
        )}
      </div>
    );
  }

  // 3. Unindexed state
  if (!isIndexed) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-[#0b0f19]">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-800 text-slate-400">
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <h3 className="mt-4 text-sm font-semibold text-slate-200">Repository Not Yet Indexed</h3>
        <p className="mt-1 text-xs text-slate-400 max-w-sm">
          Run AST code analysis on this repository to discover and resolve function CALLS edges.
        </p>
        <button
          type="button"
          onClick={onTriggerIndex}
          className="mt-4 rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500 transition shadow-sm"
        >
          Index Repository Now
        </button>
      </div>
    );
  }

  // 4. Empty call graph state
  if (subgraph.totalCallEdges === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center bg-[#0b0f19]">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#162032] border border-slate-800 text-slate-400">
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <h3 className="mt-4 text-sm font-semibold text-slate-200">No CALLS Relationships Found</h3>
        <p className="mt-1 text-xs text-slate-400 max-w-sm">
          No internal function call edges were detected in this repository. All functions may be standalone or external.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-[#0b0f19]">
      {/* Top Graph Controls Bar */}
      <div className="border-b border-slate-800 bg-[#0f172a]/90 p-3 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Left Controls: Symbol Focus Search */}
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <div className="relative flex-1">
              <input
                type="text"
                placeholder="Focus symbol in graph..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-[#162032] py-1.5 pl-8 pr-3 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
              />
              <svg
                className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>

            {callableSymbols.length > 0 && searchFilter.trim() && (
              <select
                value={focusedId || ""}
                onChange={(e) => {
                  const id = Number(e.target.value);
                  setFocusedId(id);
                  const matched = symbols.find((s) => s.id === id);
                  if (matched) onSelectSymbol(matched);
                }}
                className="rounded-lg border border-slate-700 bg-[#162032] px-2 py-1.5 text-xs text-slate-200 outline-none max-w-[180px] truncate"
              >
                <option value="">Select match...</option>
                {callableSymbols.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.symbol_type})
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Right Controls: Depth & Subgraph limit */}
          <div className="flex items-center gap-2 text-xs">
            {/* Depth Selector */}
            <div className="flex items-center rounded-lg border border-slate-800 bg-[#162032] p-0.5">
              <button
                type="button"
                onClick={() => setDepth(1)}
                className={`rounded px-2.5 py-1 text-[11px] font-medium transition ${
                  depth === 1 ? "bg-sky-600 text-white" : "text-slate-400 hover:text-white"
                }`}
                title="1-hop: Direct callers and direct callees only"
              >
                1-Hop
              </button>
              <button
                type="button"
                onClick={() => setDepth(2)}
                className={`rounded px-2.5 py-1 text-[11px] font-medium transition ${
                  depth === 2 ? "bg-sky-600 text-white" : "text-slate-400 hover:text-white"
                }`}
                title="2-hop: Callers, callees, and secondary neighbours"
              >
                2-Hop
              </button>
            </div>

            {/* Max nodes limit selector */}
            <select
              value={maxNodes}
              onChange={(e) => setMaxNodes(Number(e.target.value))}
              className="rounded-lg border border-slate-800 bg-[#162032] px-2 py-1 text-[11px] text-slate-300 outline-none"
              title="Maximum nodes in focused subgraph"
            >
              <option value={15}>15 Nodes</option>
              <option value={25}>25 Nodes</option>
              <option value={40}>40 Nodes</option>
            </select>

            {/* Reset to Primary Hub */}
            <button
              type="button"
              onClick={() => {
                setFocusedId(null);
                setSearchFilter("");
              }}
              className="rounded-lg border border-slate-800 bg-[#162032] px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:text-white hover:border-slate-700 transition"
              title="Reset focus to top connected hub"
            >
              Reset Focus
            </button>
          </div>
        </div>

        {/* Active Trace Banner */}
        {traceResult && (
          <div className="flex items-center justify-between rounded-lg bg-purple-950/70 border border-purple-800/80 px-3 py-1.5 text-xs text-purple-200 shadow-sm">
            <div className="flex items-center gap-2">
              <span className="flex h-2 w-2 rounded-full bg-purple-400 animate-pulse" />
              <span>
                Architecture Trace: <strong className="font-mono text-purple-100">{traceResult.nodes.length}</strong> steps traversed from <strong className="font-mono text-purple-300">{traceResult.startSymbol}</strong>
              </span>
            </div>
            {onClearTrace && (
              <button
                type="button"
                onClick={onClearTrace}
                className="rounded bg-purple-900/80 px-2 py-0.5 text-[10px] font-semibold text-purple-200 hover:bg-purple-800 transition border border-purple-700/60"
              >
                Clear Trace
              </button>
            )}
          </div>
        )}

        {/* Legend & Stats Banner */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800/80 pt-2 text-[11px] text-slate-400">
          <div className="flex items-center gap-3">
            {traceResult && (
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-purple-400 ring-2 ring-purple-400/30" />
                <span className="text-purple-300 font-semibold">Trace Path ({traceResult.nodes.length})</span>
              </span>
            )}
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-sky-400 ring-2 ring-sky-400/30" />
              <span className="text-slate-300">Focused</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-amber-400" />
              <span className="text-slate-300">Callers ({subgraph.directCallerIds.size})</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span className="text-slate-300">Callees ({subgraph.directCalleeIds.size})</span>
            </span>
          </div>

          <div className="flex items-center gap-2 font-mono text-[10px] text-slate-500">
            <span>
              Showing <strong className="text-slate-300">{subgraph.nodes.length}</strong> / {subgraph.totalUniqueFunctions} functions
            </span>
            <span>•</span>
            <span>
              <strong className="text-slate-300">{subgraph.edges.length}</strong> / {subgraph.totalCallEdges} calls
            </span>
          </div>
        </div>
      </div>

      {/* Interactive React Flow Canvas */}
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.2}
          maxZoom={2.0}
          proOptions={{ hideAttribution: true }}
          className="bg-[#0b0f19]"
        >
          <Background color="#1e293b" gap={24} size={1} />
          <Controls
            className="!bg-[#162032] !border-slate-700 !fill-slate-300 [&>button]:!border-slate-700 [&>button]:!bg-[#162032] [&>button]:!text-slate-300 hover:[&>button]:!bg-slate-700"
            showInteractive={false}
          />
        </ReactFlow>

        {/* Disclaimer Pill */}
        <div className="absolute bottom-3 left-3 z-10 rounded-lg bg-[#0f172a]/90 backdrop-blur border border-slate-800 px-2.5 py-1 text-[10px] text-slate-400 shadow-md">
          Static AST call relationships (codebase structure)
        </div>
      </div>
    </div>
  );
}

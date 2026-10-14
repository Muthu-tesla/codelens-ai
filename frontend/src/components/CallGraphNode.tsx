"use client";

import React, { memo } from "react";
import { Handle, Position, NodeProps, Node } from "@xyflow/react";
import { CallGraphNode as CallGraphNodeData } from "@/lib/graph-utils";

export type CustomNodeProps = Node<CallGraphNodeData>;

export const CallGraphNodeComponent = memo(function CallGraphNodeComponent({
  data,
  selected,
}: NodeProps<CustomNodeProps>) {
  const { name, qualifiedName, symbolType, relativePath, lineStart, lineEnd, role } = data;

  const isSelectedRole = role === "selected" || selected;
  const isCaller = role === "caller";
  const isCallee = role === "callee";
  const isTraceStart = role === "trace-start";
  const isTrace = role === "trace";

  let borderClasses = "border-slate-700 bg-[#162032]";
  let roleBadge = null;

  if (isTraceStart) {
    borderClasses =
      "border-purple-400 bg-[#231238] shadow-xl shadow-purple-500/25 ring-2 ring-purple-400/90";
    roleBadge = (
      <span className="rounded bg-purple-500/30 px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider text-purple-200 border border-purple-400/70">
        Step #{data.traceStep || 1} • Start
      </span>
    );
  } else if (isTrace) {
    borderClasses =
      "border-violet-500 bg-[#1a122e] shadow-lg shadow-violet-500/20 ring-1 ring-violet-400/60";
    roleBadge = (
      <span className="rounded bg-violet-500/20 px-1.5 py-0.2 text-[9px] font-semibold uppercase tracking-wider text-violet-300 border border-violet-500/50">
        Step #{data.traceStep}
      </span>
    );
  } else if (isSelectedRole) {
    borderClasses =
      "border-sky-400 bg-[#0f2847] shadow-xl shadow-sky-500/20 ring-2 ring-sky-400/80";
    roleBadge = (
      <span className="rounded bg-sky-500/30 px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider text-sky-200 border border-sky-400/60">
        Focus
      </span>
    );
  } else if (isCaller) {
    borderClasses =
      "border-amber-500/80 bg-amber-950/40 hover:border-amber-400 shadow-md shadow-amber-500/5";
    roleBadge = (
      <span className="rounded bg-amber-500/20 px-1.5 py-0.2 text-[9px] font-semibold uppercase tracking-wider text-amber-300 border border-amber-600/50">
        Caller
      </span>
    );
  } else if (isCallee) {
    borderClasses =
      "border-emerald-500/80 bg-emerald-950/40 hover:border-emerald-400 shadow-md shadow-emerald-500/5";
    roleBadge = (
      <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 text-[9px] font-semibold uppercase tracking-wider text-emerald-300 border border-emerald-600/50">
        Callee
      </span>
    );
  }

  const isMethod = symbolType.toLowerCase() === "method";

  return (
    <div
      className={`relative min-w-[220px] max-w-[260px] rounded-xl border p-3 transition duration-150 ${borderClasses}`}
    >
      {/* Target handle on Left for incoming calls */}
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !bg-amber-400 !border-slate-900"
      />

      {/* Top Header: Badge & Role */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span
            className={`rounded px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase ${
              isMethod
                ? "bg-amber-950/80 text-amber-300 border border-amber-700/60"
                : "bg-emerald-950/80 text-emerald-300 border border-emerald-700/60"
            }`}
          >
            {isMethod ? "method" : "def"}
          </span>
          {roleBadge}
        </div>

        {lineStart !== undefined && lineEnd !== undefined && (
          <span className="font-mono text-[9px] text-slate-400">
            L{lineStart}–{lineEnd}
          </span>
        )}
      </div>

      {/* Function Name */}
      <div className="mt-1.5">
        <h4
          className="truncate font-mono text-xs font-bold text-white group-hover:text-sky-300"
          title={name}
        >
          {name}
        </h4>
        <p
          className="mt-0.5 truncate font-mono text-[10px] text-slate-400"
          title={qualifiedName}
        >
          {qualifiedName}
        </p>
      </div>

      {/* Relative Path */}
      {relativePath && (
        <div className="mt-2 border-t border-slate-800/80 pt-1.5 text-[9px] font-mono text-slate-400 truncate">
          {relativePath}
        </div>
      )}

      {/* Source handle on Right for outgoing calls */}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !bg-emerald-400 !border-slate-900"
      />
    </div>
  );
});

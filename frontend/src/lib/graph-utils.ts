import type {
  ArchitectureTraceEdge,
  ArchitectureTraceNode,
  CodeRelationship,
  CodeSymbol,
  CodeSymbolBrief,
} from "../types/api.ts";

export interface CallGraphNode extends Record<string, unknown> {
  id: string; // string for React Flow node id
  symbolId: number;
  name: string;
  qualifiedName: string;
  symbolType: string;
  relativePath?: string;
  lineStart?: number;
  lineEnd?: number;
  role: "selected" | "caller" | "callee" | "neutral" | "trace" | "trace-start";
  traceStep?: number;
  position: { x: number; y: number };
}

export interface CallGraphEdge {
  id: string;
  source: string;
  target: string;
  sourceLine?: number | null;
  isHighlighted?: boolean;
  isTraceEdge?: boolean;
}

export interface SubgraphResult {
  nodes: CallGraphNode[];
  edges: CallGraphEdge[];
  totalCallEdges: number;
  totalUniqueFunctions: number;
  focusedSymbolId: number | null;
  directCallerIds: Set<number>;
  directCalleeIds: Set<number>;
  traceNodeIds?: Set<number>;
}

export interface SubgraphOptions {
  focusedSymbolId?: number | null;
  depth?: number;
  maxNodes?: number;
  traceNodes?: ArchitectureTraceNode[];
  traceEdges?: ArchitectureTraceEdge[];
  traceStartSymbol?: string;
}

export interface TraceLayoutInfo {
  depth: number;
  lane: number;
}

/**
 * Computes tree/DAG depths and branch lanes from explicit trace edges.
 * Guarantees that:
 * 1. Root symbol is at depth 0, lane 0.
 * 2. Callees are placed at depth = parent.depth + 1.
 * 3. Sibling branches are given distinct vertical lanes to prevent flattening trees into a misleading linear path.
 */
export function computeTraceNodeLayout(
  traceNodes: ArchitectureTraceNode[],
  traceEdges: ArchitectureTraceEdge[],
  traceStartSymbol?: string
): Map<string, TraceLayoutInfo> {
  const layout = new Map<string, TraceLayoutInfo>();
  if (traceNodes.length === 0) return layout;

  // Build directed outgoing adjacency from traceEdges
  const outgoing = new Map<string, string[]>();
  for (const edge of traceEdges) {
    const fromQ = edge.from || edge.from_symbol;
    const toQ = edge.to || edge.to_symbol;
    if (fromQ && toQ) {
      if (!outgoing.has(fromQ)) outgoing.set(fromQ, []);
      outgoing.get(fromQ)!.push(toQ);
    }
  }

  // Determine root symbol
  const rootNode =
    traceNodes.find((tn) => tn.qualified_name === traceStartSymbol) ||
    traceNodes.find((tn) => tn.step === 1) ||
    traceNodes[0];

  const rootQ = rootNode.qualified_name;
  layout.set(rootQ, { depth: 0, lane: 0 });

  let nextLane = 0;
  const queue: Array<{ qname: string; depth: number; lane: number }> = [
    { qname: rootQ, depth: 0, lane: 0 },
  ];
  const visited = new Set<string>([rootQ]);

  while (queue.length > 0) {
    const curr = queue.shift()!;
    const children = outgoing.get(curr.qname) || [];

    children.forEach((childQ, index) => {
      if (!visited.has(childQ)) {
        visited.add(childQ);
        // Primary child stays in current lane; subsequent branching children branch into new lanes
        const childLane = index === 0 ? curr.lane : ++nextLane;
        const childDepth = curr.depth + 1;
        layout.set(childQ, { depth: childDepth, lane: childLane });
        queue.push({ qname: childQ, depth: childDepth, lane: childLane });
      }
    });
  }

  // Fallback for any disconnected nodes
  traceNodes.forEach((tn) => {
    if (!layout.has(tn.qualified_name)) {
      layout.set(tn.qualified_name, { depth: 1, lane: ++nextLane });
    }
  });

  return layout;
}

/**
 * Filter relationships to only function/method CALLS edges.
 */
export function filterCallRelationships(relationships: CodeRelationship[]): CodeRelationship[] {
  return relationships.filter((r) => r.relationship_type.toLowerCase() === "calls");
}

/**
 * Extract a focused, readable subgraph around a selected symbol,
 * or around an active architecture trace execution path.
 */
export function extractCallSubgraph(
  relationships: CodeRelationship[],
  symbols: CodeSymbol[] = [],
  options: SubgraphOptions = {}
): SubgraphResult {
  const callEdges = filterCallRelationships(relationships);
  const maxNodes = options.maxNodes || 25;
  const depth = options.depth || 1;
  const traceNodes = options.traceNodes || [];
  const traceEdges = options.traceEdges || [];
  const traceStartSymbol = options.traceStartSymbol;

  // Build symbol metadata lookup
  const symbolLookup = new Map<number, CodeSymbol>();
  const symbolByQname = new Map<string, CodeSymbol>();
  for (const sym of symbols) {
    symbolLookup.set(sym.id, sym);
    symbolByQname.set(sym.qualified_name, sym);
  }

  // Collect all unique symbol briefs from call edges
  const allBriefs = new Map<number, CodeSymbolBrief>();
  const allBriefsByQname = new Map<string, CodeSymbolBrief>();
  const adjacencyOut = new Map<number, Set<number>>();
  const adjacencyIn = new Map<number, Set<number>>();

  for (const edge of callEdges) {
    const srcId = edge.source_symbol.id;
    const tgtId = edge.target_symbol.id;

    allBriefs.set(srcId, edge.source_symbol);
    allBriefs.set(tgtId, edge.target_symbol);
    allBriefsByQname.set(edge.source_symbol.qualified_name, edge.source_symbol);
    allBriefsByQname.set(edge.target_symbol.qualified_name, edge.target_symbol);

    if (!adjacencyOut.has(srcId)) adjacencyOut.set(srcId, new Set());
    if (!adjacencyIn.has(tgtId)) adjacencyIn.set(tgtId, new Set());

    adjacencyOut.get(srcId)!.add(tgtId);
    adjacencyIn.get(tgtId)!.add(srcId);
  }

  // Also index any trace nodes into briefs if missing
  for (const tn of traceNodes) {
    if (!allBriefsByQname.has(tn.qualified_name)) {
      const sym = symbolByQname.get(tn.qualified_name);
      const generatedId = sym ? sym.id : 900000 + tn.step;
      const brief: CodeSymbolBrief = {
        id: generatedId,
        name: tn.name,
        qualified_name: tn.qualified_name,
        symbol_type: tn.symbol_type,
      };
      allBriefs.set(generatedId, brief);
      allBriefsByQname.set(tn.qualified_name, brief);
    }
  }

  const totalCallEdges = callEdges.length;
  const totalUniqueFunctions = allBriefs.size;

  // Trace node mapping
  const traceNodeMap = new Map<number, { step: number; isStart: boolean }>();
  const traceNodeIds = new Set<number>();

  for (const tn of traceNodes) {
    const brief = allBriefsByQname.get(tn.qualified_name);
    if (brief) {
      const isStart =
        tn.step === 1 ||
        (traceStartSymbol !== undefined && tn.qualified_name === traceStartSymbol);
      traceNodeMap.set(brief.id, { step: tn.step, isStart });
      traceNodeIds.add(brief.id);
    }
  }

  // If there are trace nodes, focus defaults to the trace start symbol
  let focusId = options.focusedSymbolId ?? null;
  if (traceNodes.length > 0 && (!focusId || !traceNodeIds.has(focusId))) {
    const startTn = traceNodes.find((tn) => tn.step === 1) || traceNodes[0];
    const startBrief = allBriefsByQname.get(startTn.qualified_name);
    if (startBrief) {
      focusId = startBrief.id;
    }
  }

  // Fallback to highest-degree symbol if no focus and no trace
  if (focusId === null && totalCallEdges > 0) {
    let bestDegree = -1;
    let bestId: number | null = null;
    for (const id of allBriefs.keys()) {
      const deg = (adjacencyOut.get(id)?.size || 0) + (adjacencyIn.get(id)?.size || 0);
      if (deg > bestDegree) {
        bestDegree = deg;
        bestId = id;
      }
    }
    focusId = bestId;
  }

  const includedNodeIds = new Set<number>();
  const directCallerIds = new Set<number>();
  const directCalleeIds = new Set<number>();

  // If trace is active: include all trace nodes first!
  for (const tid of traceNodeIds) {
    includedNodeIds.add(tid);
  }

  if (focusId !== null) {
    includedNodeIds.add(focusId);

    // 1-hop callers (incoming to focus)
    const callers = adjacencyIn.get(focusId) || new Set();
    for (const cid of callers) {
      if (includedNodeIds.size >= maxNodes) break;
      includedNodeIds.add(cid);
      directCallerIds.add(cid);
    }

    // 1-hop callees (outgoing from focus)
    const callees = adjacencyOut.get(focusId) || new Set();
    for (const cid of callees) {
      if (includedNodeIds.size >= maxNodes) break;
      includedNodeIds.add(cid);
      directCalleeIds.add(cid);
    }

    // 2-hop exploration if depth >= 2
    if (depth >= 2 && includedNodeIds.size < maxNodes) {
      for (const c1 of Array.from(directCalleeIds)) {
        const c2s = adjacencyOut.get(c1) || new Set();
        for (const c2 of c2s) {
          if (includedNodeIds.size >= maxNodes) break;
          includedNodeIds.add(c2);
        }
      }
      for (const c1 of Array.from(directCallerIds)) {
        const c2s = adjacencyIn.get(c1) || new Set();
        for (const c2 of c2s) {
          if (includedNodeIds.size >= maxNodes) break;
          includedNodeIds.add(c2);
        }
      }
    }
  }

  // Build trace edge lookup
  const traceEdgeSet = new Set<string>();
  for (const te of traceEdges) {
    const fromQ = te.from || te.from_symbol;
    const toQ = te.to || te.to_symbol;
    if (fromQ && toQ) {
      traceEdgeSet.add(`${fromQ}->${toQ}`);
    }
  }

  // Filter edges to those between included nodes
  const filteredEdges: CallGraphEdge[] = [];
  const edgeDedupe = new Set<string>();

  for (const edge of callEdges) {
    const srcId = edge.source_symbol.id;
    const tgtId = edge.target_symbol.id;

    if (includedNodeIds.has(srcId) && includedNodeIds.has(tgtId)) {
      const edgeKey = `${srcId}->${tgtId}`;
      if (!edgeDedupe.has(edgeKey)) {
        edgeDedupe.add(edgeKey);
        const qnameKey = `${edge.source_symbol.qualified_name}->${edge.target_symbol.qualified_name}`;
        const isTrace = traceEdgeSet.has(qnameKey);
        // When active trace is present, only actual trace edges should be highlighted.
        // Unrelated edges are never highlighted as trace execution paths.
        const isHighlighted =
          traceNodes.length > 0
            ? isTrace
            : focusId !== null && (srcId === focusId || tgtId === focusId);

        filteredEdges.push({
          id: `e-${edge.id || edgeKey}`,
          source: String(srcId),
          target: String(tgtId),
          sourceLine: edge.source_line,
          isHighlighted,
          isTraceEdge: isTrace,
        });
      }
    }
  }

  // Ensure all explicit trace edges are present even if not in repository call relationships
  for (const te of traceEdges) {
    const fromQ = te.from || te.from_symbol;
    const toQ = te.to || te.to_symbol;
    if (fromQ && toQ) {
      const srcBrief = allBriefsByQname.get(fromQ);
      const tgtBrief = allBriefsByQname.get(toQ);
      if (srcBrief && tgtBrief) {
        const edgeKey = `${srcBrief.id}->${tgtBrief.id}`;
        if (!edgeDedupe.has(edgeKey)) {
          edgeDedupe.add(edgeKey);
          filteredEdges.push({
            id: `trace-e-${srcBrief.id}-${tgtBrief.id}`,
            source: String(srcBrief.id),
            target: String(tgtBrief.id),
            sourceLine: te.source_line,
            isHighlighted: true,
            isTraceEdge: true,
          });
        }
      }
    }
  }

  // Layout arrangement:
  // If active trace is present, arrange trace nodes using tree/DAG hierarchical placement
  // preserving branching depths and parallel branch lanes (no flattening into a linear conveyor).
  const nodes: CallGraphNode[] = [];
  const ROW_HEIGHT = 105;
  const X_STEP = 340;
  const LANE_HEIGHT = 135;

  if (traceNodes.length > 0) {
    const traceLayout = computeTraceNodeLayout(traceNodes, traceEdges, traceStartSymbol);
    let maxLane = 0;

    traceNodes.forEach((tn) => {
      const brief = allBriefsByQname.get(tn.qualified_name);
      if (!brief) return;

      const sym = symbolLookup.get(brief.id);
      const isStart = tn.step === 1 || tn.qualified_name === traceStartSymbol;
      const posInfo = traceLayout.get(tn.qualified_name) || { depth: 0, lane: 0 };
      if (posInfo.lane > maxLane) maxLane = posInfo.lane;

      nodes.push({
        id: String(brief.id),
        symbolId: brief.id,
        name: tn.name,
        qualifiedName: tn.qualified_name,
        symbolType: tn.symbol_type,
        relativePath: tn.file || sym?.relative_path || undefined,
        lineStart: tn.line_start ?? sym?.line_start ?? undefined,
        lineEnd: tn.line_end ?? sym?.line_end ?? undefined,
        role: isStart ? "trace-start" : "trace",
        traceStep: tn.step,
        position: {
          x: 50 + posInfo.depth * X_STEP,
          y: 60 + posInfo.lane * LANE_HEIGHT,
        },
      });
    });

    // Layout non-trace caller/callee nodes below the trace hierarchy
    const nonTraceNodes = Array.from(includedNodeIds).filter((id) => !traceNodeIds.has(id));
    const startY = 80 + (maxLane + 1) * LANE_HEIGHT;
    nonTraceNodes.forEach((id, index) => {
      const brief = allBriefs.get(id);
      if (!brief) return;
      const meta = symbolLookup.get(id);

      nodes.push({
        id: String(id),
        symbolId: id,
        name: brief.name,
        qualifiedName: brief.qualified_name,
        symbolType: brief.symbol_type,
        relativePath: meta?.relative_path || undefined,
        lineStart: meta?.line_start,
        lineEnd: meta?.line_end,
        role: "neutral",
        position: {
          x: 50,
          y: startY + index * ROW_HEIGHT,
        },
      });
    });
  } else {
    // Normal layered layout around focused symbol
    const callerNodes: number[] = [];
    const calleeNodes: number[] = [];
    const otherNodes: number[] = [];

    for (const id of includedNodeIds) {
      if (id === focusId) continue;
      if (directCallerIds.has(id)) {
        callerNodes.push(id);
      } else if (directCalleeIds.has(id)) {
        calleeNodes.push(id);
      } else {
        otherNodes.push(id);
      }
    }

    // Callers (Layer 0)
    callerNodes.forEach((id, index) => {
      const brief = allBriefs.get(id)!;
      const meta = symbolLookup.get(id);
      nodes.push({
        id: String(id),
        symbolId: id,
        name: brief.name,
        qualifiedName: brief.qualified_name,
        symbolType: brief.symbol_type,
        relativePath: meta?.relative_path || undefined,
        lineStart: meta?.line_start,
        lineEnd: meta?.line_end,
        role: "caller",
        position: { x: 50, y: index * ROW_HEIGHT + 50 },
      });
    });

    // Focused Node (Layer 1)
    if (focusId !== null && allBriefs.has(focusId)) {
      const brief = allBriefs.get(focusId)!;
      const meta = symbolLookup.get(focusId);
      const maxRows = Math.max(callerNodes.length, calleeNodes.length, 1);
      const centerY = ((maxRows - 1) * ROW_HEIGHT) / 2 + 50;

      nodes.push({
        id: String(focusId),
        symbolId: focusId,
        name: brief.name,
        qualifiedName: brief.qualified_name,
        symbolType: brief.symbol_type,
        relativePath: meta?.relative_path || undefined,
        lineStart: meta?.line_start,
        lineEnd: meta?.line_end,
        role: "selected",
        position: { x: 50 + X_STEP, y: centerY },
      });
    }

    // Callees (Layer 2)
    calleeNodes.forEach((id, index) => {
      const brief = allBriefs.get(id)!;
      const meta = symbolLookup.get(id);
      nodes.push({
        id: String(id),
        symbolId: id,
        name: brief.name,
        qualifiedName: brief.qualified_name,
        symbolType: brief.symbol_type,
        relativePath: meta?.relative_path || undefined,
        lineStart: meta?.line_start,
        lineEnd: meta?.line_end,
        role: "callee",
        position: { x: 50 + X_STEP * 2, y: index * ROW_HEIGHT + 50 },
      });
    });

    // Others (Layer 3)
    otherNodes.forEach((id, index) => {
      const brief = allBriefs.get(id)!;
      const meta = symbolLookup.get(id);
      nodes.push({
        id: String(id),
        symbolId: id,
        name: brief.name,
        qualifiedName: brief.qualified_name,
        symbolType: brief.symbol_type,
        relativePath: meta?.relative_path || undefined,
        lineStart: meta?.line_start,
        lineEnd: meta?.line_end,
        role: "neutral",
        position: { x: 50 + X_STEP * 3, y: index * ROW_HEIGHT + 50 },
      });
    });
  }

  return {
    nodes,
    edges: filteredEdges,
    totalCallEdges,
    totalUniqueFunctions,
    focusedSymbolId: focusId,
    directCallerIds,
    directCalleeIds,
    traceNodeIds,
  };
}

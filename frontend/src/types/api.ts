export interface Repository {
  id: number;
  name: string;
  path: string;
  created_at: string;
}

export interface RepositoryCreateInput {
  name: string;
  path: string;
}

export interface FileMetadata {
  relative_path: string;
  extension: string;
  size_bytes: number;
  line_count: number;
}

export interface RepositoryFilesResponse {
  repository_id: number;
  total_files: number;
  files: FileMetadata[];
}

export interface RepositoryAnalysisSummary {
  repository_id: number;
  files_analyzed: number;
  python_files: number;
  classes: number;
  functions: number;
  methods: number;
  imports: number;
  relationships: number;
  call_relationships: number;
  chunks_created: number;
  embeddings_generated: number;
  errors: string[];
}

export type SymbolType = "module" | "class" | "function" | "method" | string;

export interface CodeSymbol {
  id: number;
  file_id: number;
  relative_path: string | null;
  qualified_name: string;
  name: string;
  symbol_type: SymbolType;
  line_start: number;
  line_end: number;
  signature: string | null;
  docstring: string | null;
  created_at: string;
}

export interface CodeSymbolBrief {
  id: number;
  name: string;
  qualified_name: string;
  symbol_type: string;
}

export interface CodeRelationship {
  id: number;
  repository_id: number;
  relationship_type: "contains" | "inherits" | "imports" | "calls" | string;
  source_line: number | null;
  source_symbol: CodeSymbolBrief;
  target_symbol: CodeSymbolBrief;
  created_at: string;
}

export interface CodeSymbolDetail extends CodeSymbol {
  relative_path: string;
  outgoing_relationships: CodeRelationship[];
  incoming_relationships: CodeRelationship[];
}

export interface RepositoryStatus {
  repository: Repository;
  isIndexed: boolean;
  symbolCount: number;
  fileCount: number;
  isAnalyzing?: boolean;
}

export interface ArchitectureTraceNode {
  step: number;
  qualified_name: string;
  name: string;
  symbol_type: string;
  file: string;
  line_start?: number | null;
  line_end?: number | null;
  signature?: string | null;
}

export interface ArchitectureTraceEdge {
  from?: string;
  from_symbol?: string;
  to?: string;
  to_symbol?: string;
  relationship: string;
  source_line?: number | null;
}

export interface ArchitectureTraceResponse {
  start_symbol: string;
  nodes: ArchitectureTraceNode[];
  edges: ArchitectureTraceEdge[];
  summary: string;
}

export interface EvidenceItem {
  id: string;
  file: string;
  qualified_name?: string | null;
  symbol_type?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  content: string;
  similarity?: number | null;
}

export interface ArchitectureExplainTrace {
  start_symbol: string;
  nodes: ArchitectureTraceNode[];
  edges: ArchitectureTraceEdge[];
}

export interface ArchitectureExplainResponse {
  question: string;
  answer: string;
  trace: ArchitectureExplainTrace | null;
  evidence: EvidenceItem[];
}

// Analysis domain types (Phase 2), mirroring the backend AnalysisOut / SSE events.
import type { ArtifactSpec } from "@insightflow/artifact-schema";

export type AnalysisStatus = "pending" | "running" | "completed" | "error";

export interface SqlToolResult {
  columns?: string[];
  rows?: unknown[][];
  row_count?: number;
  truncated?: boolean;
  error?: string;
  // Python tool may return arbitrary JSON keys (output / summary / etc.)
  [key: string]: unknown;
}

export interface AgentEndResult {
  answer: string;
  steps: { tool: string; sql?: string; result?: SqlToolResult }[];
  sql_results: { sql?: string; result?: SqlToolResult }[];
  tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface AgentStartEvent {
  type: "agent_start";
  agent?: string;
}
export interface ToolStartEvent {
  type: "tool_start";
  tool?: string;
  input?: { sql?: string; code?: string };
}
export interface ToolEndEvent {
  type: "tool_end";
  tool?: string;
  result?: SqlToolResult;
}
export interface MessageEvent {
  type: "message";
  content?: string;
}
export interface ErrorEvent {
  type: "error";
  message?: string;
}
export interface AgentActivityEvent {
  type: "agent_activity";
  agent?: string;
  status?: string;
  content?: string;
}
export interface AgentEndEvent {
  type: "agent_end";
  status: string;
  answer?: string;
  error?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  tool_calls?: number;
  retries?: number;
  latency_ms?: number;
  content?: string;
  result?: AgentEndResult;
}

export interface ChartSpec {
  renderer: "echarts" | "r3f";
  type: string; // bar | line | pie | scatter | histogram | area | ...
  title?: string;
  xField?: string | string[];
  yField?: string | string[];
  zField?: string;
  data: Array<Record<string, unknown>>;
  dimensions?: string[];
  seriesOptions?: Record<string, unknown>;
}

// Agent2UI：Agent 直接输出的可执行 UI（TSX），不再是枚举式 ChartSpec。
export interface ChartEvent {
  type: "chart";
  spec: ArtifactSpec;
}

// ---- Phase 6: Agent Trace ----
export interface AgentRunSummary {
  id: string;
  analysis_id: string;
  thread_id: string;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost: number;
  latency_ms: number;
  tool_calls: number;
  retries: number;
  created_at: string | null;
  finished_at: string | null;
}

export interface AgentTraceStep {
  id: string;
  agent: string;
  step_type: string; // agent | message | tool | chart | error
  content: string | null;
  input: unknown;
  output: unknown;
  status: string;
  tokens: number;
  duration_ms: number;
  ts_ms: number;
  order_idx: number;
}

export interface ToolCallRecord {
  id: string;
  tool: string;
  input: unknown;
  output: unknown;
  status: string;
  duration_ms: number;
  ts_ms: number;
}

export interface AnalysisTrace {
  run: AgentRunSummary;
  steps: AgentTraceStep[];
  tool_calls: ToolCallRecord[];
}

export type AnalysisEvent =
  | AgentStartEvent
  | AgentActivityEvent
  | ToolStartEvent
  | ToolEndEvent
  | MessageEvent
  | ErrorEvent
  | AgentEndEvent
  | ChartEvent;

export interface AnalysisOut {
  id: string;
  dataset_id: string;
  dataset_ids: string[];
  query: string;
  status: AnalysisStatus;
  answer: string;
  result: Record<string, unknown>;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string;
  updated_at: string;
}

// ---- Phase 7: Analysis Report ----
export interface ReportEvidence {
  title?: string;
  sql?: string | null;
  columns?: string[];
  rows?: unknown[][];
}

export interface ReportMetrics {
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  tool_calls: number;
  cost: number;
}

export interface AnalysisReport {
  query: string;
  dataset_name: string;
  generated_at?: string;
  executive_summary: string;
  key_findings: string[];
  evidence: ReportEvidence[];
  charts: ChartSpec[];
  recommendations: string[];
  limitations?: string | null;
  metrics: ReportMetrics;
}

export interface ReportOut {
  id: string;
  analysis_id: string;
  format: string;
  content: AnalysisReport;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string | null;
}

// ---- 历史分析列表 / 详情 ----
export interface AnalysisSummary {
  id: string;
  dataset_id: string;
  dataset_ids: string[];
  query: string;
  status: AnalysisStatus;
  answer: string;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface AnalysisDetail {
  id: string;
  dataset_id: string;
  dataset_ids: string[];
  query: string;
  status: AnalysisStatus;
  answer: string;
  result: Record<string, unknown>;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string;
  updated_at: string;
}

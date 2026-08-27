import type { DatasetDetail, DatasetSummary } from "@/types/dataset";
import type {
  AnalysisEvent,
  AnalysisOut,
  AnalysisSummary,
  AnalysisTrace,
  AnalysisReport,
  ReportOut,
} from "@/types/analysis";

export type {
  AnalysisEvent,
  AnalysisOut,
  AnalysisSummary,
  AnalysisTrace,
  AnalysisReport,
  ReportOut,
} from "@/types/analysis";

// Empty default => all calls go through Next's same-origin proxy (see next.config.ts).
// Set NEXT_PUBLIC_API_URL to an absolute URL only for non-proxied deployments.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

/** Attach the current access token (if any) to an outgoing request. */
export function authHeaders(
  init?: RequestInit | undefined,
): RequestInit | undefined {
  const token = typeof window !== "undefined"
    ? window.localStorage.getItem("if_access_token")
    : null;
  if (!token) return init;
  return {
    ...init,
    headers: { ...(init?.headers ?? {}), Authorization: `Bearer ${token}` },
  };
}

/** Thin wrapper around fetch that forwards the current auth token. */
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit | undefined,
): Promise<Response> {
  return fetch(input, authHeaders(init));
}

export async function parseError(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = body.detail ?? detail;
  } catch {
    /* ignore */
  }
  throw new Error(`${res.status}: ${detail}`);
}

/** Convert any thrown value into a human-readable message for the UI. */
export function errMsg(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  return "发生未知错误";
}

export async function listDatasets(): Promise<DatasetSummary[]> {
  const res = await apiFetch(`${API_BASE}/api/v1/datasets`);
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getDataset(id: string): Promise<DatasetDetail> {
  const res = await apiFetch(`${API_BASE}/api/v1/datasets/${id}`);
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function uploadDataset(
  file: File,
  name?: string,
): Promise<DatasetDetail> {
  const form = new FormData();
  form.append("file", file);
  if (name) form.append("name", name);
  const res = await apiFetch(`${API_BASE}/api/v1/datasets`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function deleteDataset(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/v1/datasets/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) return parseError(res);
}

export interface ConnectDBPayload {
  name: string;
  db_type: "postgres" | "mysql" | "sqlite";
  host?: string | null;
  port?: number | null;
  username?: string | null;
  password?: string | null;
  database?: string | null;
  schema?: string | null;
  table: string;
}

/** 直连数据库并把指定表物化为数据集。 */
export async function connectDatabase(
  payload: ConnectDBPayload,
): Promise<DatasetDetail> {
  const res = await apiFetch(`${API_BASE}/api/v1/datasets/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await apiFetch(`${API_BASE}/health`);
  if (!res.ok) return parseError(res);
  return res.json();
}

// ---- InsightFlow 2.0: data profile & semantic layer ----

export interface DatasetProfile2 {
  dataset_id: string;
  quality_score: number;
  issues: Array<{
    column: string;
    category: string;
    severity: "high" | "medium" | "low";
    message: string;
    suggestion?: string;
  }>;
  schema: {
    roles: Record<string, string>;
    relations: Array<{
      left_col: string;
      right_col: string;
      relation_type: string;
      strength: number;
    }>;
    columns: Array<{ name: string; type: string }>;
  };
  anomalies: Array<{
    column: string;
    kind: string;
    severity: string;
    count?: number;
    value?: unknown;
    message: string;
  }>;
  generated_at?: string | null;
}

export interface SemanticLayer {
  dataset_id: string;
  metrics: Array<{
    id: string;
    name: string;
    column: string;
    aggregation: string;
    sql_expr: string;
    unit: string;
    description: string;
    status: "auto" | "confirmed";
  }>;
  dimensions: Array<{
    id: string;
    name: string;
    column: string;
    is_time: boolean;
    granularity: string;
    description: string;
    status: "auto" | "confirmed";
  }>;
}

export async function getDatasetProfile2(id: string): Promise<DatasetProfile2> {
  const res = await apiFetch(`${API_BASE}/api/v1/datasets/${id}/profile`, {
    cache: "no-store",
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getDatasetSemantics(id: string): Promise<SemanticLayer> {
  const res = await apiFetch(`${API_BASE}/api/v1/datasets/${id}/semantics`, {
    cache: "no-store",
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function confirmSemantic(
  datasetId: string,
  itemType: "metric" | "dimension",
  itemId: string,
): Promise<{ id: string; type: string; status: string }> {
  const res = await apiFetch(
    `${API_BASE}/api/v1/datasets/${datasetId}/semantics/${itemType}/${itemId}/confirm`,
    { method: "PATCH" },
  );
  if (!res.ok) return parseError(res);
  return res.json();
}

export interface Insight2 {
  id: string;
  dataset_id: string;
  kind: string;
  title: string;
  conclusion: string;
  metric: string;
  dimensions: string[];
  evidence: {
    claim?: string;
    result?: string;
    confidence?: number;
    [k: string]: unknown;
  };
  confidence: number;
  severity: "high" | "medium" | "low";
  sql: string;
  created_at?: string | null;
}

export interface InsightsResponse {
  dataset_id: string;
  insights: Insight2[];
}

export async function getDatasetInsights(id: string): Promise<InsightsResponse> {
  const res = await apiFetch(`${API_BASE}/api/v1/datasets/${id}/insights`, {
    cache: "no-store",
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

// —— 2.0 evidence chain & root cause ——

/** Shape of a persisted evidence tool result (rows + row_count + columns). */
export interface EvidenceResult {
  rows?: unknown[][];
  row_count?: number;
  columns?: string[];
  [k: string]: unknown;
}

export interface EvidenceRow {
  id: string;
  dataset_id: string;
  analysis_id: string | null;
  claim: string;
  metric: string;
  dimensions: string[];
  source: "sql" | "python";
  sql: string;
  result: EvidenceResult;
  confidence: number;
  created_at?: string | null;
}

export interface EvidencesResponse {
  analysis_id: string;
  evidences: EvidenceRow[];
}

export interface RootCausePayload {
  id?: string;
  dataset_id?: string;
  question: string;
  change: {
    metric: string;
    delta: number;
    base_value: number;
    current_value: number;
    significant: boolean;
    reason: string;
  };
  contributions: {
    factor: string;
    contribution: number;
    contribution_pct: number;
    metric: string;
    period: string;
  }[];
  factors: string[];
  hypotheses: {
    hypothesis: string;
    status: "已证实" | "待验证";
    evidence_ids?: string[];
  }[];
  conclusion: string;
  confidence: number;
  created_at?: string | null;
}

export interface RootCauseResponse {
  analysis_id: string;
  root_cause: RootCausePayload | null;
}

export async function getAnalysisEvidences(
  id: string
): Promise<EvidencesResponse> {
  const res = await apiFetch(`${API_BASE}/api/v1/analyses/${id}/evidences`, {
    cache: "no-store",
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getAnalysisRootCause(
  id: string
): Promise<RootCauseResponse> {
  const res = await apiFetch(`${API_BASE}/api/v1/analyses/${id}/root-cause`, {
    cache: "no-store",
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export interface EvidenceGraphNode {
  id: string;
  claim: string;
  metric: string;
  source: string;
  sql: string;
  confidence: number;
  parent_id: string | null;
  level: number;
  result: EvidenceResult;
}

export interface EvidenceGraphResponse {
  analysis_id: string;
  nodes: EvidenceGraphNode[];
  edges: { from: string; to: string }[];
}

export async function getEvidenceGraph(
  id: string
): Promise<EvidenceGraphResponse> {
  const res = await apiFetch(`${API_BASE}/api/v1/analyses/${id}/evidence-graph`, {
    cache: "no-store",
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function createAnalysis(
  datasetIds: string[],
  query: string,
): Promise<AnalysisOut> {
  const res = await apiFetch(`${API_BASE}/api/v1/analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_ids: datasetIds, query }),
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisOut> {
  const res = await apiFetch(`${API_BASE}/api/v1/analyses/${id}`);
  if (!res.ok) return parseError(res);
  return res.json();
}

/** List past analyses, optionally filtered by dataset. Newest first. */
export async function listAnalyses(
  datasetId?: string,
  limit = 50,
): Promise<AnalysisSummary[]> {
  const params = new URLSearchParams();
  if (datasetId) params.set("dataset_id", datasetId);
  params.set("limit", String(limit));
  const res = await apiFetch(
    `${API_BASE}/api/v1/analyses?${params.toString()}`,
    { method: "GET" },
  );
  if (!res.ok) return parseError(res);
  return res.json();
}

/** Stream a running analysis via SSE, invoking `onEvent` for each parsed event. */
export async function runAnalysisStream(
  id: string,
  onEvent: (ev: AnalysisEvent) => void,
): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/v1/analyses/${id}/run`, {
    method: "POST",
  });
  if (!res.ok) return parseError(res);
  if (!res.body) throw new Error("no response stream");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of chunk.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") continue;
        try {
          onEvent(JSON.parse(payload) as AnalysisEvent);
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  }
}

export async function getAnalysisTrace(id: string): Promise<AnalysisTrace> {
  const res = await apiFetch(`${API_BASE}/api/v1/analyses/${id}/trace`, {
    cache: "no-store",
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

// ---- Phase 7: report ----

/** Race a promise against a timeout so a hanging request can't spin forever. */
function withTimeout<T>(p: Promise<T>, ms: number, msg: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(msg)), ms);
    p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      }
    );
  });
}

export async function getReport(id: string): Promise<AnalysisReport | null> {
  const res = await withTimeout(
    apiFetch(`${API_BASE}/api/v1/analyses/${id}/report`, { cache: "no-store" }),
    30000,
    "加载报告超时，请稍后重试"
  );
  if (res.status === 404) return null;
  if (!res.ok) return parseError(res);
  const body = (await res.json()) as ReportOut;
  return body.content;
}

export async function createReport(id: string): Promise<AnalysisReport> {
  const res = await withTimeout(
    apiFetch(`${API_BASE}/api/v1/analyses/${id}/report`, { method: "POST" }),
    120000,
    "报告生成超时（模型响应较慢），请点击重试"
  );
  if (res.status === 409) throw new Error("分析尚未完成，暂不能生成报告");
  if (!res.ok) return parseError(res);
  const body = (await res.json()) as ReportOut;
  return body.content;
}

export type ReportExportFormat = "html" | "markdown";

/** Open the standalone report in a new tab (inline) or trigger a download. */
export function reportExportUrl(
  id: string,
  inline = false,
  format: ReportExportFormat = "html",
): string {
  const params = new URLSearchParams();
  if (format && format !== "html") params.set("format", format);
  if (inline) params.set("inline", "true");
  const qs = params.toString();
  return `${API_BASE}/api/v1/analyses/${id}/report/export${qs ? `?${qs}` : ""}`;
}

/** Trigger a browser download of the standalone report (HTML or Markdown). */
export function downloadReport(
  id: string,
  filename = "report.html",
  format: ReportExportFormat = "html",
): void {
  const a = document.createElement("a");
  a.href = reportExportUrl(id, false, format);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** Download the evidence-driven report as Markdown. */
export function downloadReportMarkdown(id: string): void {
  downloadReport(id, "insightflow-report.md", "markdown");
}

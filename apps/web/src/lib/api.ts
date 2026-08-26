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
  const res = await fetch(`${API_BASE}/api/v1/datasets`);
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getDataset(id: string): Promise<DatasetDetail> {
  const res = await fetch(`${API_BASE}/api/v1/datasets/${id}`);
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
  const res = await fetch(`${API_BASE}/api/v1/datasets`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function deleteDataset(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/datasets/${id}`, {
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
  const res = await fetch(`${API_BASE}/api/v1/datasets/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function createAnalysis(
  datasetIds: string[],
  query: string,
): Promise<AnalysisOut> {
  const res = await fetch(`${API_BASE}/api/v1/analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_ids: datasetIds, query }),
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisOut> {
  const res = await fetch(`${API_BASE}/api/v1/analyses/${id}`);
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
  const res = await fetch(
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
  const res = await fetch(`${API_BASE}/api/v1/analyses/${id}/run`, {
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
  const res = await fetch(`${API_BASE}/api/v1/analyses/${id}/trace`, {
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
    fetch(`${API_BASE}/api/v1/analyses/${id}/report`, { cache: "no-store" }),
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
    fetch(`${API_BASE}/api/v1/analyses/${id}/report`, { method: "POST" }),
    120000,
    "报告生成超时（模型响应较慢），请点击重试"
  );
  if (res.status === 409) throw new Error("分析尚未完成，暂不能生成报告");
  if (!res.ok) return parseError(res);
  const body = (await res.json()) as ReportOut;
  return body.content;
}

/** Open the standalone HTML report in a new tab (inline) or trigger a download. */
export function reportExportUrl(id: string, inline = false): string {
  return `${API_BASE}/api/v1/analyses/${id}/report/export${
    inline ? "?inline=true" : ""
  }`;
}

/** Trigger a browser download of the standalone HTML report. */
export function downloadReport(id: string, filename = "report.html"): void {
  const a = document.createElement("a");
  a.href = reportExportUrl(id, false);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

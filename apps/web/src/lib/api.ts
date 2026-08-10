import type { DatasetDetail, DatasetSummary } from "@/types/dataset";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function parseError(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    detail = body.detail ?? detail;
  } catch {
    /* ignore */
  }
  throw new Error(`${res.status}: ${detail}`);
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

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) return parseError(res);
  return res.json();
}

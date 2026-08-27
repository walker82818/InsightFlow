"use client";

import { useEffect, useState } from "react";
import {
  listAnalyses,
  getAnalysis,
  getReport,
  createReport,
  getAnalysisTrace,
} from "@/lib/api";
import type { AnalysisSummary, AnalysisReport } from "@/types/analysis";
import { HistoryPayload } from "@/components/HistoryDetail";

const STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  error: "失败",
  running: "分析中",
  pending: "排队中",
};

function timeAgo(iso: string, now: number): string {
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return iso;
  const sec = Math.max(0, Math.floor((now - d) / 1000));
  if (sec < 60) return "刚刚";
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  if (sec < 86400 * 30) return `${Math.floor(sec / 86400)} 天前`;
  return new Date(d).toLocaleDateString("zh-CN");
}

export default function AnalysisHistory({
  datasetId,
  refreshSignal = 0,
  onSelect,
  onSelectLoading,
}: {
  datasetId: string;
  refreshSignal?: number;
  onSelect?: (payload: HistoryPayload | null) => void;
  onSelectLoading?: (loading: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [list, setList] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const rows = await listAnalyses(datasetId);
        if (!cancelled) setList(rows);
      } catch {
        if (!cancelled) setLoadError("历史加载失败，请稍后重试");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId, refreshSignal]);

  async function selectRow(row: AnalysisSummary) {
    if (selectedId === row.id) {
      setSelectedId(null);
      onSelect?.(null);
      return;
    }
    setSelectedId(row.id);
    onSelectLoading?.(true);
    let detail = null;
    let report: AnalysisReport | null = null;
    let trace = null;
    try {
      detail = await getAnalysis(row.id);
    } catch {
      detail = null;
    }
    try {
      report = await getReport(row.id);
      if (!report) report = await createReport(row.id);
    } catch {
      report = null;
    }
    try {
      trace = await getAnalysisTrace(row.id);
    } catch {
      trace = null;
    }
    onSelectLoading?.(false);
    if (detail) onSelect?.({ detail, report, trace });
  }

  function closeSelection() {
    setSelectedId(null);
    onSelect?.(null);
  }

  // 当父组件清空选中（如点击返回），同步列表高亮由 selectedId 状态驱动
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between text-sm font-semibold text-ink"
        >
          <span>历史分析（{list.length}）</span>
          <span className="text-faint">{open ? "收起" : "展开"}</span>
        </button>
      </div>

      {open && (
        <div className="mt-3 space-y-2">
          {loading && (
            <div className="space-y-2">
              <div className="skeleton h-14 w-full rounded-xl" />
              <div className="skeleton h-14 w-full rounded-xl" />
            </div>
          )}

          {loadError && (
            <p className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
              {loadError}
            </p>
          )}

          {!loading && !loadError && list.length === 0 && (
            <p className="rounded-xl border border-dashed border-line px-3 py-4 text-center text-xs text-faint">
              还没有历史分析。每次提问后，结论会自动归档到这里，方便随时回看。
            </p>
          )}

          {list.map((row) => {
            const active = selectedId === row.id;
            return (
              <button
                key={row.id}
                onClick={() => selectRow(row)}
                className={`block w-full rounded-xl border px-3 py-2.5 text-left transition ${
                  active
                    ? "border-accent bg-accent-soft/40"
                    : "border-line hover:border-line-strong hover:bg-surface-2"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="line-clamp-1 text-sm font-medium text-ink">
                    {row.query}
                  </span>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${
                      row.status === "completed"
                        ? "tag-pine"
                        : row.status === "error"
                          ? "tag-danger"
                          : row.status === "running"
                            ? "tag-amber"
                            : "tag"
                    }`}
                  >
                    {STATUS_LABEL[row.status] ?? row.status}
                  </span>
                </div>

                {row.answer && (
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-faint">
                    {row.answer}
                  </p>
                )}

                <div className="mt-1.5 flex items-center gap-3 text-[11px] text-faint">
                  <span title={new Date(row.updated_at).toLocaleString("zh-CN")}>
                    {timeAgo(row.updated_at, now)}
                  </span>
                  {(row.prompt_tokens + row.completion_tokens) > 0 && (
                    <span>≈ {row.prompt_tokens + row.completion_tokens} tokens</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {selectedId && (
        <button
          onClick={closeSelection}
          className="mt-3 w-full text-xs text-faint hover:text-ink"
        >
          关闭当前历史
        </button>
      )}
    </div>
  );
}

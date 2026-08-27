"use client";

import { useEffect, useState, use } from "react";
import { getDataset, errMsg } from "@/lib/api";
import type { DatasetDetail } from "@/types/dataset";
import AnalysisChat from "@/components/AnalysisChat";
import AnalysisHistory from "@/components/AnalysisHistory";
import HistoryDetail, { type HistoryPayload } from "@/components/HistoryDetail";
import DatasetSnapshotBar from "@/components/DatasetSnapshotBar";
import SemanticLayerPanel from "@/components/SemanticLayerPanel";
import InsightsPanel from "@/components/InsightsPanel";

export default function DatasetPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ ids?: string }>;
}) {
  const { id } = use(params);
  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [historySignal, setHistorySignal] = useState(0);
  const [history, setHistory] = useState<HistoryPayload | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Extra tables carried in via ?ids=a,b,c — primary `id` is always first.
  const [extraIds, setExtraIds] = useState<string[]>([]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const sp = await searchParams;
      if (cancelled) return;
      const list = (sp.ids ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .filter((x) => x !== id);
      setExtraIds(list);
    })();
    return () => {
      cancelled = true;
    };
  }, [searchParams, id]);
  const datasetIds = [id, ...extraIds];

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await getDataset(id);
        if (!cancelled) setDataset(d);
      } catch (e) {
        if (!cancelled) setLoadError(errMsg(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loadError) {
    return (
      <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
        <div className="text-danger">加载失败：{loadError}</div>
        <button className="btn btn-ghost" onClick={() => location.reload()}>
          重试
        </button>
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-24 w-full rounded-[28px]" />
        <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
          <div className="skeleton h-[60vh] w-full rounded-[24px]" />
          <div className="skeleton h-[60vh] w-full rounded-[24px]" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <section className="card fade-up p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="eyebrow">
              数据集 · {dataset.row_count} 行 · {dataset.column_count} 列 ·{" "}
              <span className="uppercase">{dataset.file_type}</span>
            </div>
            <h1 className="mt-1 font-display text-2xl font-bold tracking-tight text-ink">
              {dataset.name}
            </h1>
          </div>
          <span className="tag tag-pine shrink-0">就绪</span>
        </div>

      </section>

      {/* Data snapshot —— 全宽数据健康概览（质量分 + 统计 + 字段角色 + 可展开明细） */}
      <DatasetSnapshotBar dataset={dataset} />

      {/* Main grid —— 主对话区（左）常驻；历史详情以覆盖层嵌在主对话区内，不改变整体布局 */}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="relative">
          <AnalysisChat
            datasetIds={datasetIds}
            onAddDataset={(newId) =>
              setExtraIds((prev) =>
                prev.includes(newId) ? prev : [...prev, newId]
              )
            }
            onRemoveDataset={(rmId) => {
              if (rmId === id) return; // keep the primary table anchored
              setExtraIds((prev) => prev.filter((x) => x !== rmId));
            }}
            onAnalysisDone={() => setHistorySignal((n) => n + 1)}
          />
          {historyLoading && !history && (
            <div className="absolute inset-0 z-40 flex items-center justify-center rounded-[24px] bg-paper/80">
              <div className="card px-6 py-4 text-sm text-muted">正在加载历史分析…</div>
            </div>
          )}
          {history && (
            <div className="absolute inset-0 z-50 overflow-auto rounded-[24px] bg-paper p-5 shadow-inner">
              <HistoryDetail payload={history} onBack={() => setHistory(null)} />
            </div>
          )}
        </div>
        <aside className="space-y-6">
          <InsightsPanel datasetId={id} />
          <SemanticLayerPanel datasetId={id} />
          <AnalysisHistory
            datasetId={id}
            refreshSignal={historySignal}
            onSelect={setHistory}
            onSelectLoading={setHistoryLoading}
          />
        </aside>
      </div>
    </div>
  );
}

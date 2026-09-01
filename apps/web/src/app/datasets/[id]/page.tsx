"use client";

import { useEffect, useState, use } from "react";
import type { ReactNode } from "react";
import { getDataset, errMsg } from "@/lib/api";
import type { DatasetDetail } from "@/types/dataset";
import AnalysisChat from "@/components/AnalysisChat";
import AnalysisHistory from "@/components/AnalysisHistory";
import HistoryDetail, { type HistoryPayload } from "@/components/HistoryDetail";
import DatasetSnapshotBar from "@/components/DatasetSnapshotBar";
import SemanticLayerPanel from "@/components/SemanticLayerPanel";
import InsightsPanel from "@/components/InsightsPanel";

type Side = "insights" | "semantic" | "history";

const SIDE_LABEL: Record<Side, string> = {
  insights: "主动洞察",
  semantic: "语义层",
  history: "历史分析",
};

const SIDE_ICON: Record<Side, ReactNode> = {
  insights: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.6.5 1 1.4 1 2.5h6c0-1.1.4-2 1-2.5A6 6 0 0 0 12 3Z" />
    </svg>
  ),
  semantic: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3 3 8l9 5 9-5-9-5ZM3 13l9 5 9-5M3 18l9 5 9-5" />
    </svg>
  ),
  history: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  ),
};

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
  const [showSnapshot, setShowSnapshot] = useState(false);
  const [side, setSide] = useState<Side | null>(null);

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
      <div className="card mx-auto max-w-6xl flex-col items-center gap-3 px-6 py-16 text-center">
        <div className="text-danger">加载失败：{loadError}</div>
        <button className="btn btn-ghost" onClick={() => location.reload()}>
          重试
        </button>
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="mx-auto max-w-[90rem] space-y-4">
        <div className="skeleton h-14 w-full rounded-[18px]" />
        <div className="skeleton h-[60vh] w-full rounded-[18px]" />
      </div>
    );
  }

  return (
    /* 对话工作台：全宽对话为主体，辅助信息（快照/洞察/语义/历史）全部收纳为按需入口 */
    <div className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-[90rem] flex-col gap-4">
      {/* Masthead —— 数据集身份 + 快照入口 + 辅助抽屉开关（不占卡片，直接浮于画布之上） */}
      <header className="fade-up flex flex-wrap items-center gap-x-5 gap-y-2 px-2 py-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-accent to-accent-strong text-white shadow-[0_10px_24px_-10px_rgba(217,83,46,0.55)]">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3v18h18M7 14l3-3 3 3 5-6" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h1 className="truncate font-display text-[22px] font-bold leading-tight tracking-tight text-ink">
                {dataset.name}
              </h1>
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-pine-soft px-2 py-0.5 text-[11px] font-semibold text-pine">
                <span className="h-1.5 w-1.5 rounded-full bg-pine" />
                已就绪
              </span>
            </div>
            <div className="mt-1 text-xs text-faint">
              {dataset.row_count.toLocaleString()} 行 · {dataset.column_count} 列 ·{" "}
              <span className="uppercase">{dataset.file_type}</span>
            </div>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowSnapshot((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-[13px] font-semibold transition ${
              showSnapshot
                ? "border-accent bg-accent-soft/60 text-accent-strong"
                : "border-transparent bg-surface text-muted shadow-sm hover:border-line-strong hover:text-ink"
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3v18h18M8 17V9M13 17V5M18 17v-6" />
            </svg>
            {showSnapshot ? "收起快照" : "数据快照"}
          </button>

          {(Object.keys(SIDE_LABEL) as Side[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setSide(side === k ? null : k)}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-[13px] font-semibold transition ${
                side === k
                  ? "border-accent bg-accent-soft/60 text-accent-strong"
                  : "border-transparent bg-surface text-muted shadow-sm hover:border-line-strong hover:text-ink"
              }`}
            >
              {SIDE_ICON[k]}
              {SIDE_LABEL[k]}
            </button>
          ))}
        </div>
      </header>

      {/* 数据快照 —— 按需展开（默认折叠，让对话拥有最大空间） */}
      {showSnapshot && <DatasetSnapshotBar dataset={dataset} />}

      {/* 对话主体（全宽）+ 右侧辅助抽屉 + 历史详情覆盖层 */}
      <div className="relative min-h-0 flex-1 overflow-hidden">
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
          <div className="absolute inset-0 z-40 flex items-center justify-center rounded-[18px] bg-paper/80">
            <div className="card px-6 py-4 text-sm text-muted">正在加载历史分析…</div>
          </div>
        )}

        {history && (
          <div className="absolute inset-0 z-50 overflow-auto rounded-[18px] bg-paper p-5 shadow-inner">
            <HistoryDetail payload={history} onBack={() => setHistory(null)} />
          </div>
        )}

        {/* 抽屉遮罩 */}
        {side && (
          <div
            className="absolute inset-0 z-30 rounded-[18px] bg-ink/10"
            onClick={() => setSide(null)}
            aria-hidden
          />
        )}

        {/* 右侧滑入抽屉 —— 辅助面板不挤压对话，按需展开 */}
        <aside
          className={`absolute inset-y-0 right-0 z-40 flex w-[340px] max-w-[85%] flex-col overflow-hidden rounded-l-[18px] border-l border-line bg-paper shadow-2xl transition-transform duration-300 ease-out ${
            side ? "translate-x-0" : "translate-x-full"
          }`}
          aria-hidden={!side}
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div className="flex items-center gap-2">
              {SIDE_ICON[side ?? "insights"]}
              <span className="font-display text-sm font-bold text-ink">
                {SIDE_LABEL[side ?? "insights"]}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSide(null)}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-muted transition hover:bg-paper-2 hover:text-ink"
              aria-label="关闭面板"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {side === "insights" && <InsightsPanel datasetId={id} />}
            {side === "semantic" && <SemanticLayerPanel datasetId={id} />}
            {side === "history" && (
              <AnalysisHistory
                datasetId={id}
                refreshSignal={historySignal}
                onSelect={setHistory}
                onSelectLoading={setHistoryLoading}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

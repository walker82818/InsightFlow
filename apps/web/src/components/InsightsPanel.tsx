"use client";

import { useEffect, useState } from "react";
import { getDatasetInsights, errMsg } from "@/lib/api";
import type { InsightsResponse } from "@/lib/api";

const KIND_LABEL: Record<string, string> = {
  trend: "趋势",
  anomaly: "异常",
  distribution_shift: "分布偏移",
  top_contribution: "贡献占比",
  correlation: "相关性",
  quality: "数据质量",
};

const SEV_DOT: Record<string, string> = {
  high: "bg-danger",
  medium: "bg-amber",
  low: "bg-pine",
};

const KIND_ICON: Record<string, string> = {
  trend: "↗",
  anomaly: "❗",
  distribution_shift: "⇄",
  top_contribution: "◆",
  correlation: "⤫",
  quality: "◐",
};

export default function InsightsPanel({ datasetId }: { datasetId: string }) {
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const d = await getDatasetInsights(datasetId);
        if (!cancelled) setData(d);
      } catch (e) {
        if (!cancelled) {
          setError(errMsg(e));
          setData(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (loading) {
    return (
      <div className="card p-4">
        <div className="skeleton h-4 w-1/3" />
        <div className="skeleton mt-3 h-20 w-full" />
        <div className="skeleton mt-2 h-20 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card p-4">
        <div className="eyebrow">主动洞察</div>
        <div className="mt-2 text-xs text-muted">
          {error ?? "暂无洞察，请重新上传数据集。"}
        </div>
      </div>
    );
  }

  const insights = data.insights;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="eyebrow">主动洞察</div>
        <span className="text-xs text-faint">{insights.length} 条</span>
      </div>
      <p className="mt-1 text-xs text-faint">
        上传后自动发现的趋势、异常与关联，无需提问。
      </p>

      {insights.length === 0 ? (
        <div className="mt-3 rounded-xl bg-surface-2 px-3 py-3 text-xs text-muted">
          暂未发现可自动沉淀的洞察。
        </div>
      ) : (
        <div className="mt-3 max-h-[26rem] space-y-2 overflow-auto pr-1">
          {insights.map((ins) => (
            <div
              key={ins.id}
              className="rounded-xl border border-line bg-surface px-3 py-2.5"
            >
              <div className="flex items-start gap-2">
                <span
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] text-white ${
                    SEV_DOT[ins.severity] ?? "bg-pine"
                  }`}
                  aria-hidden
                >
                  {KIND_ICON[ins.kind] ?? "•"}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold text-ink">
                      {ins.title}
                    </span>
                    <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">
                      {KIND_LABEL[ins.kind] ?? ins.kind}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted">
                    {ins.conclusion}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-faint">
                    {ins.evidence?.result && (
                      <span className="font-mono">
                        依据：{ins.evidence.result}
                      </span>
                    )}
                    <span>置信 {Math.round(ins.confidence * 100)}%</span>
                    {ins.dimensions.length > 0 && (
                      <span>维度：{ins.dimensions.join("、")}</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

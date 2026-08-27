"use client";

import { useEffect, useState } from "react";
import { getDatasetSemantics, confirmSemantic, errMsg } from "@/lib/api";
import type { SemanticLayer } from "@/lib/api";

export default function SemanticLayerPanel({
  datasetId,
}: {
  datasetId: string;
}) {
  const [sem, setSem] = useState<SemanticLayer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const s = await getDatasetSemantics(datasetId);
        if (!cancelled) setSem(s);
      } catch (e) {
        if (!cancelled) {
          setError(errMsg(e));
          setSem(null);
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
      </div>
    );
  }

  if (error || !sem) {
    return (
      <div className="card p-4">
        <div className="eyebrow">语义层</div>
        <div className="mt-2 text-xs text-muted">
          {error ?? "暂无语义层定义。"}
        </div>
      </div>
    );
  }

  const handleConfirm = async (type: "metric" | "dimension", id: string) => {
    setConfirmingId(id);
    setActionMsg(null);
    try {
      await confirmSemantic(datasetId, type, id);
      setSem((prev) => {
        if (!prev) return prev;
        const patch = (items: { id: string; status: string }[]) =>
          items.map((it) => (it.id === id ? { ...it, status: "confirmed" } : it));
        return type === "metric"
          ? { ...prev, metrics: patch(prev.metrics) as SemanticLayer["metrics"] }
          : { ...prev, dimensions: patch(prev.dimensions) as SemanticLayer["dimensions"] };
      });
    } catch (e) {
      setActionMsg(errMsg(e));
    } finally {
      setConfirmingId(null);
    }
  };

  const ConfirmBtn = ({ type, id }: { type: "metric" | "dimension"; id: string }) => (
    <button
      onClick={() => handleConfirm(type, id)}
      disabled={confirmingId === id}
      className="btn ml-2 !px-2 !py-0.5 !text-[11px]"
    >
      {confirmingId === id ? "确认中…" : "确认"}
    </button>
  );

  const renderMetric = (m: SemanticLayer["metrics"][number]) => (
    <div
      key={m.id}
      className="flex items-center justify-between rounded-xl border border-line bg-surface px-3 py-2"
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-ink">{m.name}</div>
        <div className="truncate font-mono text-[11px] text-muted">
          {m.sql_expr || `${m.aggregation}(${m.column})`}
        </div>
      </div>
      <span
        className={`tag ml-2 !py-0 !text-[10px] ${
          m.status === "confirmed" ? "tag-pine" : "tag-amber"
        }`}
      >
        {m.status === "confirmed" ? "已确认" : "自动"}
      </span>
      {m.status !== "confirmed" && <ConfirmBtn type="metric" id={m.id} />}
    </div>
  );

  const renderDimension = (d: SemanticLayer["dimensions"][number]) => (
    <div
      key={d.id}
      className="flex items-center justify-between rounded-xl border border-line bg-surface px-3 py-2"
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-ink">{d.name}</div>
        <div className="truncate text-[11px] text-muted">
          {d.is_time ? `时间 · ${d.granularity || "日"}` : "分类维度"}
        </div>
      </div>
      <span
        className={`tag ml-2 !py-0 !text-[10px] ${
          d.status === "confirmed" ? "tag-pine" : "tag-amber"
        }`}
      >
        {d.status === "confirmed" ? "已确认" : "自动"}
      </span>
      {d.status !== "confirmed" && <ConfirmBtn type="dimension" id={d.id} />}
    </div>
  );

  return (
    <div className="card p-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <div>
          <div className="eyebrow">语义层</div>
          <div className="mt-0.5 text-xs text-faint">
            {sem.metrics.length} 指标 · {sem.dimensions.length} 维度
          </div>
        </div>
        <span
          className={`text-faint transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
          aria-hidden
        >
          ▾
        </span>
      </button>

      {open && (
        <>
          <div className="mt-3">
            <div className="mb-1.5 text-xs text-muted">
              指标 · {sem.metrics.length}
            </div>
            <div className="space-y-1.5">
              {sem.metrics.length === 0 ? (
                <div className="rounded-xl bg-surface-2 px-3 py-2 text-xs text-muted">
                  暂无指标
                </div>
              ) : (
                sem.metrics.map(renderMetric)
              )}
            </div>
          </div>

          <div className="mt-3">
            <div className="mb-1.5 text-xs text-muted">
              维度 · {sem.dimensions.length}
            </div>
            <div className="space-y-1.5">
              {sem.dimensions.length === 0 ? (
                <div className="rounded-xl bg-surface-2 px-3 py-2 text-xs text-muted">
                  暂无维度
                </div>
              ) : (
                sem.dimensions.map(renderDimension)
              )}
            </div>
          </div>

          {actionMsg && (
            <div className="mt-3 rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">
              {actionMsg}
            </div>
          )}
        </>
      )}
    </div>
  );
}

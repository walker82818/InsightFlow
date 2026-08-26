"use client";

import type { DatasetDetail } from "@/types/dataset";

const TYPE_LABEL: Record<string, string> = {
  string: "文本",
  integer: "整数",
  float: "小数",
  date: "日期",
  category: "类别",
  boolean: "布尔",
};

export default function DatasetStructureView({
  dataset,
}: {
  dataset: DatasetDetail | null;
}) {
  if (!dataset) {
    return (
      <div className="card p-4">
        <div className="skeleton h-4 w-1/3" />
        <div className="skeleton mt-3 h-24 w-full" />
      </div>
    );
  }

  const profile = dataset.profile;
  const missing = profile?.total_missing ?? 0;
  const dup = profile?.duplicate_rows ?? 0;

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="eyebrow">数据结构</div>
        <span className="text-xs text-faint">
          {dataset.row_count} 行 · {dataset.column_count} 列
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-line bg-surface-2 p-2.5">
          <div className="text-xs text-muted">缺失值</div>
          <div className="font-display text-base font-bold text-ink">{missing}</div>
        </div>
        <div className="rounded-xl border border-line bg-surface-2 p-2.5">
          <div className="text-xs text-muted">重复行</div>
          <div className="font-display text-base font-bold text-ink">{dup}</div>
        </div>
      </div>

      <div className="mt-3 max-h-72 space-y-1.5 overflow-auto pr-1">
        {dataset.columns.map((c) => (
          <div
            key={c.name}
            className="flex items-center justify-between rounded-lg border border-line bg-surface px-3 py-2"
          >
            <span className="truncate text-sm font-medium text-ink">{c.name}</span>
            <span className="tag !py-0.5 !text-[11px]">
              {TYPE_LABEL[c.type] ?? c.type}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

"use client";

import type { DatasetSummary } from "@/types/dataset";

const STATUS_LABEL: Record<string, string> = {
  ready: "就绪",
  processing: "处理中",
  error: "异常",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DatasetCard({ dataset }: { dataset: DatasetSummary }) {
  const ready = dataset.status === "ready";
  return (
    <div className="card group h-full p-5 transition duration-300 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-lg">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-display text-base font-semibold text-ink">
            {dataset.name}
          </div>
          <div className="mt-0.5 text-xs text-faint">{dataset.file_name}</div>
        </div>
        <div className="flex shrink-0 items-start gap-2">
          {dataset.source_type === "db" && (
            <span className="tag !py-0.5 !text-[11px]">
              数据库{dataset.db_info?.db_type ? ` · ${dataset.db_info.db_type}` : ""}
            </span>
          )}
          <span className={`tag ${ready ? "tag-pine" : "tag-amber"}`}>
            {STATUS_LABEL[dataset.status] ?? dataset.status}
          </span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span>
          <span className="font-semibold text-ink-soft">{dataset.row_count}</span> 行
        </span>
        <span>
          <span className="font-semibold text-ink-soft">{dataset.column_count}</span> 列
        </span>
        <span>{formatSize(dataset.file_size)}</span>
        <span className="uppercase">{dataset.file_type}</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {dataset.columns.slice(0, 4).map((c) => (
          <span key={c.name} className="tag !py-0.5 !text-[11px]">
            {c.name}
          </span>
        ))}
        {dataset.columns.length > 4 && (
          <span className="tag !py-0.5 !text-[11px] text-faint">
            +{dataset.columns.length - 4}
          </span>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-xs text-faint">
        <span>更新于 {new Date(dataset.created_at).toLocaleDateString("zh-CN")}</span>
        <span className="flex items-center gap-1 text-accent-strong opacity-0 transition group-hover:opacity-100">
          打开
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </span>
      </div>
    </div>
  );
}

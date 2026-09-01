"use client";

import { useEffect, useState } from "react";
import { getDatasetProfile2, errMsg } from "@/lib/api";
import type { DatasetDetail } from "@/types/dataset";
import type { DatasetProfile2 } from "@/lib/api";

const ROLE_LABEL: Record<string, string> = {
  id: "ID",
  time: "时间",
  dimension: "维度",
  metric: "指标",
  numeric_dimension: "数值维度",
  text: "文本",
};

function scoreColor(score: number) {
  if (score >= 90) return { text: "text-pine", bar: "bg-pine" };
  if (score >= 75) return { text: "text-amber", bar: "bg-amber" };
  return { text: "text-danger", bar: "bg-danger" };
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-[0.08em] text-faint">
        {label}
      </div>
      <div className="mt-0.5 truncate font-display text-lg font-bold leading-tight text-ink">
        {value}
      </div>
      {hint && <div className="text-[11px] text-faint">{hint}</div>}
    </div>
  );
}

const TYPE_LABEL: Record<string, string> = {
  string: "文本",
  integer: "整数",
  float: "小数",
  date: "日期",
  category: "类别",
  boolean: "布尔",
};

const ISSUE_LABEL: Record<string, string> = {
  missing: "缺失",
  type_mismatch: "类型",
  duplicate: "重复",
  outlier: "离群",
  invalid: "非法",
};

export default function DatasetSnapshotBar({
  dataset,
}: {
  dataset: DatasetDetail;
}) {
  const [profile, setProfile] = useState<DatasetProfile2 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false); // 整个快照卡展开/收起
  const [detailOpen, setDetailOpen] = useState(false); // 字段与质量明细

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getDatasetProfile2(dataset.id);
        if (!cancelled) setProfile(p);
      } catch (e) {
        if (!cancelled) setError(errMsg(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dataset.id]);

  const missing = dataset.profile?.total_missing ?? 0;
  const dup = dataset.profile?.duplicate_rows ?? 0;
  const issues = profile?.issues.length ?? 0;
  const score = profile?.quality_score;
  const roles = profile?.schema.roles ?? {};
  const roleEntries = Object.entries(roles);
  const scoreUI = score != null ? scoreColor(score) : null;

  return (
    <section className="card fade-up overflow-hidden">
      {/* 概览行 —— 默认收起，把垂直空间让给对话区 */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-4 px-5 py-3 text-left transition hover:bg-paper-2/50"
        aria-expanded={open}
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 3v18h18M7 14l3-3 3 3 5-6" />
          </svg>
        </span>
        <span className="min-w-0 flex-1">
          <span className="block">
            <span className="eyebrow">数据快照</span>
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-sm text-ink-soft">
            <span className="font-display font-bold text-ink">
              {dataset.row_count.toLocaleString()} 行
            </span>
            <span className="text-faint">·</span>
            <span>{dataset.column_count} 列</span>
            <span className="text-faint">·</span>
            <span>缺失 {missing.toLocaleString()}</span>
            {score != null && (
              <>
                <span className="text-faint">·</span>
                <span>
                  质量
                  <span className={`font-semibold ${scoreUI?.text}`}>
                    {" "}
                    {score}
                  </span>
                  /100
                </span>
              </>
            )}
            {issues > 0 && (
              <>
                <span className="text-faint">·</span>
                <span className="text-danger">{issues} 处问题</span>
              </>
            )}
            <span className="text-faint">·</span>
            <span>{roleEntries.length} 类角色</span>
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted">
          {open ? "收起" : "查看详情"}
          <span
            className={`text-faint transition-transform duration-200 ${
              open ? "rotate-180" : ""
            }`}
            aria-hidden
          >
            ▾
          </span>
        </span>
      </button>

      {open && (
        <div className="border-t border-line px-6 py-5">
          {/* Quality score + primary stats */}
          <div className="flex items-center gap-7">
            <div className="w-28 shrink-0">
              <div className="eyebrow">数据质量</div>
              {score != null ? (
                <>
                  <div
                    className={`font-display text-3xl font-bold leading-tight ${
                      scoreUI?.text
                    }`}
                  >
                    {score}
                    <span className="ml-0.5 align-baseline text-sm font-medium text-faint">
                      /100
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-paper-2">
                    <div
                      className={`h-full rounded-full ${scoreUI?.bar} transition-all duration-500`}
                      style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
                    />
                  </div>
                </>
              ) : (
                <div className="mt-2 text-xs text-faint">
                  {error ?? "加载中…"}
                </div>
              )}
            </div>

            <div className="hidden h-12 w-px bg-line sm:block" aria-hidden />

            <div className="grid grid-cols-2 gap-x-7 gap-y-3 sm:grid-cols-4">
              <Stat label="行数" value={dataset.row_count} />
              <Stat label="列数" value={dataset.column_count} />
              <Stat label="缺失值" value={missing} hint="总量" />
              <Stat
                label="重复行"
                value={dup}
                hint={issues ? `${issues} 处问题` : "无问题"}
              />
            </div>
          </div>

          {/* Field roles as a compact chip cloud */}
          <div className="mt-5 min-w-0">
            <div className="eyebrow mb-2">字段角色</div>
            <div className="flex max-w-xl flex-wrap gap-1.5">
              {roleEntries.length > 0 ? (
                roleEntries.map(([col, role]) => (
                  <span key={col} className="tag" title={col}>
                    <span className="text-faint">{col}</span>
                    <span className="ml-1">{ROLE_LABEL[role] ?? role}</span>
                  </span>
                ))
              ) : (
                <span className="text-xs text-faint">
                  {error ?? "加载角色…"}
                </span>
              )}
            </div>
          </div>

          {/* Expandable field & quality detail */}
          <div className="mt-5 border-t border-line pt-4">
            <button
              type="button"
              onClick={() => setDetailOpen((v) => !v)}
              className="flex w-full items-center justify-between text-sm font-medium text-ink"
            >
              <span>字段与质量明细</span>
              <span
                className={`text-faint transition-transform duration-200 ${
                  detailOpen ? "rotate-180" : ""
                }`}
                aria-hidden
              >
                ▾
              </span>
            </button>

            {detailOpen && (
              <div className="mt-4 grid gap-5 lg:grid-cols-2">
                {/* Column list */}
                <div>
                  <div className="eyebrow mb-2">字段清单</div>
                  <div className="max-h-64 space-y-1.5 overflow-auto pr-1">
                    {dataset.columns.map((c) => (
                      <div
                        key={c.name}
                        className="flex items-center justify-between rounded-lg border border-line bg-surface px-3 py-2"
                      >
                        <span className="truncate text-sm font-medium text-ink">
                          {c.name}
                        </span>
                        <span className="tag !py-0.5 !text-[11px]">
                          {TYPE_LABEL[c.type] ?? c.type}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Quality issues */}
                <div>
                  <div className="eyebrow mb-2">
                    质量问题{issues ? ` · ${issues}` : ""}
                  </div>
                  {(profile?.issues?.length ?? 0) > 0 ? (
                    <div className="space-y-1.5">
                      {(profile?.issues ?? []).map((iss, i) => (
                        <div
                          key={i}
                          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm"
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[11px] font-semibold ${
                                iss.severity === "high"
                                  ? "text-danger"
                                  : iss.severity === "medium"
                                  ? "text-amber"
                                  : "text-faint"
                              }`}
                            >
                              {ISSUE_LABEL[iss.category] ?? iss.category}
                            </span>
                            <span className="truncate text-muted">
                              {iss.column}
                            </span>
                          </div>
                          <div className="mt-0.5 text-xs text-faint">
                            {iss.message}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-faint">
                      {error ?? "未发现质量问题"}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

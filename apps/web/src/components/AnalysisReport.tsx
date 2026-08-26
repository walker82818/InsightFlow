"use client";

import type { AnalysisReport, ChartSpec, ReportEvidence } from "@/types/analysis";
import ChartRenderer from "@/components/ChartRenderer";

function SectionTitle({
  index,
  children,
}: {
  index?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      {index !== undefined && (
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-ink text-xs font-bold text-paper">
          {index}
        </span>
      )}
      <h3 className="font-display text-lg font-semibold text-ink">{children}</h3>
    </div>
  );
}

function EvidenceTable({
  columns,
  rows,
}: {
  columns?: string[];
  rows?: unknown[][];
}) {
  if (!columns || columns.length === 0) return null;
  return (
    <div className="mt-2 max-h-56 overflow-auto rounded-xl border border-line">
      <table className="w-full border-collapse text-left text-xs">
        <thead className="sticky top-0 bg-surface-2">
          <tr>
            {columns.map((c) => (
              <th key={c} className="whitespace-nowrap px-3 py-2 font-semibold text-ink-soft">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(rows ?? []).map((row, i) => (
            <tr key={i} className="border-t border-line">
              {columns.map((_, j) => (
                <td key={j} className="whitespace-nowrap px-3 py-1.5 text-ink-soft">
                  {String(row?.[j] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AnalysisReportView({ report }: { report: AnalysisReport }) {
  const findings = report.key_findings ?? [];
  const charts = report.charts ?? [];
  const evidence = report.evidence ?? [];
  const recs = report.recommendations ?? [];
  const limits = report.limitations
    ? String(report.limitations)
        .split(/\n+/)
        .map((s) => s.trim())
        .filter(Boolean)
    : [];
  const m = report.metrics;
  const totalTokens = (m?.prompt_tokens ?? 0) + (m?.completion_tokens ?? 0);

  return (
    <article className="space-y-8">
      {/* Hero */}
      <header className="fade-up">
        <div className="eyebrow">分析报告</div>
        <h2 className="mt-1 font-display text-2xl font-bold leading-snug text-ink">
          {report.query}
        </h2>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
          {report.dataset_name && (
            <span className="tag">数据集 · {report.dataset_name}</span>
          )}
          {report.generated_at && (
            <span className="tag">
              {new Date(report.generated_at).toLocaleString("zh-CN")}
            </span>
          )}
          <span className="tag-accent">AI 生成</span>
        </div>
      </header>

      {/* Metrics strip */}
      {m && (
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4 fade-up">
          <div className="tile p-4">
            <div className="text-xs text-muted">Token 总量</div>
            <div className="mt-1 font-display text-2xl font-bold text-ink">
              {totalTokens.toLocaleString()}
            </div>
          </div>
          <div className="tile p-4">
            <div className="text-xs text-muted">耗时</div>
            <div className="mt-1 font-display text-2xl font-bold text-ink">
              {((m.latency_ms ?? 0) / 1000).toFixed(1)}
              <span className="ml-0.5 text-sm text-muted">s</span>
            </div>
          </div>
          <div className="tile p-4">
            <div className="text-xs text-muted">工具调用</div>
            <div className="mt-1 font-display text-2xl font-bold text-ink">
              {m.tool_calls ?? 0}
            </div>
          </div>
          <div className="tile p-4">
            <div className="text-xs text-muted">预估费用</div>
            <div className="mt-1 font-display text-2xl font-bold text-ink">
              ${(m.cost ?? 0).toFixed(4)}
            </div>
          </div>
        </section>
      )}

      {/* Executive summary */}
      {report.executive_summary && (
        <section className="fade-up">
          <SectionTitle>概述</SectionTitle>
          <p className="whitespace-pre-wrap border-l-2 border-accent pl-4 text-[15px] font-medium leading-relaxed text-ink">
            {report.executive_summary}
          </p>
        </section>
      )}

      {/* Key findings */}
      {findings.length > 0 && (
        <section className="fade-up">
          <SectionTitle>关键发现</SectionTitle>
          <div className="space-y-3">
            {findings.map((f, i) => (
              <div key={i} className="tile p-4">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 font-display text-lg font-bold text-accent">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <p className="text-sm leading-relaxed text-ink-soft">{f}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Charts */}
      {charts.length > 0 && (
        <section className="fade-up">
          <SectionTitle>可视化</SectionTitle>
          <div className="grid gap-4 md:grid-cols-2">
            {charts.map((c: ChartSpec, i) => (
              <div key={i} className="card overflow-hidden p-4">
                <div className="mb-2 text-sm font-semibold text-ink-soft">
                  {c.title}
                </div>
                <ChartRenderer spec={c} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Evidence */}
      {evidence.length > 0 && (
        <section className="fade-up">
          <SectionTitle>数据证据</SectionTitle>
          <div className="space-y-3">
            {evidence.map((e: ReportEvidence, i) => (
              <div key={i} className="tile p-4">
                <div className="text-sm font-medium text-ink">
                  {e.title ?? "证据"}
                </div>
                {e.sql && (
                  <pre className="mt-2 overflow-auto rounded-lg bg-ink px-3 py-2 text-xs leading-relaxed text-paper/90">
                    {e.sql}
                  </pre>
                )}
                <EvidenceTable columns={e.columns} rows={e.rows} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Recommendations */}
      {recs.length > 0 && (
        <section className="fade-up">
          <SectionTitle>建议</SectionTitle>
          <ul className="space-y-2">
            {recs.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-ink-soft">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-pine" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Limitations */}
      {limits.length > 0 && (
        <section className="fade-up">
          <SectionTitle>局限与说明</SectionTitle>
          <ul className="space-y-2">
            {limits.map((l, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-muted">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-faint" />
                <span>{l}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="border-t border-line pt-4 text-xs text-faint">
        本报告由本地大模型基于本次分析结果自动生成，仅供参考，请结合业务实际判断。
      </p>
    </article>
  );
}

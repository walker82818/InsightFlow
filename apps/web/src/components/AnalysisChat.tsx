"use client";

import { useEffect, useRef, useState } from "react";
import {
  createAnalysis,
  runAnalysisStream,
  getReport,
  createReport,
  downloadReport,
  downloadReportMarkdown,
  reportExportUrl,
  listDatasets,
} from "@/lib/api";
import type { DatasetSummary } from "@/types/dataset";
import type {
  AnalysisEvent,
  AnalysisTrace,
  AnalysisReport,
} from "@/types/analysis";
import AnalysisReportView from "@/components/AnalysisReport";
import AgentTrace from "@/components/AgentTrace";
import EvidencePanel from "@/components/EvidencePanel";
import Markdown from "@/components/Markdown";

type Tab = "chat" | "report" | "trace";
type Status = "idle" | "running" | "completed" | "error";

const EXAMPLES = [
  "各地区的销售额对比如何？",
  "用户留存率随时间怎么变化？",
  "哪些因素最影响转化？",
  "给我一份完整的分析报告",
];

const STATUS_META: Record<Status, { label: string; cls: string }> = {
  idle: { label: "待开始", cls: "tag" },
  running: { label: "分析中", cls: "tag-amber" },
  completed: { label: "已完成", cls: "tag-pine" },
  error: { label: "出错", cls: "tag-danger" },
};

export default function AnalysisChat({
  datasetIds,
  seed,
  onAddDataset,
  onRemoveDataset,
  onAnalysisDone,
}: {
  datasetIds: string[];
  seed?: string;
  onAddDataset?: (id: string) => void;
  onRemoveDataset?: (id: string) => void;
  onAnalysisDone?: () => void;
}) {
  const [tab, setTab] = useState<Tab>("chat");
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [seedOpen, setSeedOpen] = useState(false);
  const [seedText, setSeedText] = useState(seed ?? "");
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [trace, setTrace] = useState<AnalysisTrace | null>(null);
  const [allDatasets, setAllDatasets] = useState<DatasetSummary[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);

  // Load the full dataset list once, so the user can append more tables later.
  useEffect(() => {
    let cancelled = false;
    listDatasets()
      .then((list) => {
        if (!cancelled) setAllDatasets(list);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const nameOf = (id: string) =>
    allDatasets.find((d) => d.id === id)?.name ?? "数据表";

  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportAttempted, setReportAttempted] = useState(false);
  const reportStartedRef = useRef<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [events, tab]);

  // Auto-build the report after a successful analysis so it's ready on the
  // report tab; robust against the effect re-cancelling itself.
  async function generateReport(id: string | null) {
    if (!id || reportLoading) return;
    if (reportStartedRef.current === id && report) return;
    setReportLoading(true);
    setReportError(null);
    setReportAttempted(false);
    try {
      const r = await createReport(id);
      setReport(r);
      reportStartedRef.current = id;
    } catch (e) {
      setReportError((e as Error).message);
    } finally {
      setReportLoading(false);
      setReportAttempted(true);
    }
  }

  // Load report when the user opens the report tab. Note: `reportLoading`
  // is intentionally NOT a dependency — flipping it would re-run this effect
  // and cancel the in-flight request (the old bug that left "生成 / 加载报告中…" forever).
  useEffect(() => {
    if (tab !== "report" || !analysisId) return;
    if (report || reportAttempted) return;
    if (reportStartedRef.current === analysisId) return;
    if (status === "running") {
      setReportAttempted(true);
      return;
    }
    let cancelled = false;
    (async () => {
      setReportLoading(true);
      setReportError(null);
      try {
        const r = await getReport(analysisId);
        if (cancelled) return;
        if (r) {
          setReport(r);
          reportStartedRef.current = analysisId;
        } else {
          await generateReport(analysisId);
        }
      } catch (e) {
        if (!cancelled) setReportError((e as Error).message);
      } finally {
        if (!cancelled) {
          setReportLoading(false);
          setReportAttempted(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, analysisId, report, reportAttempted, status]);

  async function send(q: string) {
    const base = q.trim();
    if (!base || loading) return;
    if (datasetIds.length === 0) {
      setQuery("请先选择至少一张数据表");
      return;
    }
    const text = seedText.trim()
      ? `${base}\n\n[分析侧重] ${seedText.trim()}`
      : base;
    setEvents([]);
    setTrace(null);
    setStatus("running");
    setLoading(true);
    setReport(null);
    setReportAttempted(false);
    setReportError(null);
    setReportLoading(false);
    reportStartedRef.current = null;
    setTab("chat");
    try {
      const created = await createAnalysis(datasetIds, text);
      setAnalysisId(created.id);
      await runAnalysisStream(created.id, (ev) => {
        setEvents((prev) => [...prev, ev]);
        if (ev.type === "agent_end")
          setStatus(ev.status === "error" ? "error" : "completed");
        if (ev.type === "error") setStatus("error");
      });
      setStatus((s) => (s === "running" ? "completed" : s));
      generateReport(created.id);
      onAnalysisDone?.();
    } catch (e) {
      setStatus("error");
      setReportError((e as Error).message);
      setReportAttempted(true);
    } finally {
      setLoading(false);
    }
  }

  function buildTrace(): AnalysisTrace | null {
    if (events.length === 0) return null;
    const steps: AnalysisTrace["steps"] = events
      .filter(
        (e): e is Extract<AnalysisEvent, { type: "agent_activity" }> =>
          e.type === "agent_activity"
      )
      .map((e, i) => ({
        id: String(i),
        agent: e.agent ?? "agent",
        step_type: "agent",
        content: e.content ?? null,
        input: null,
        output: null,
        status: e.status ?? "success",
        tokens: 0,
        duration_ms: 0,
        ts_ms: 0,
        order_idx: i,
      }));
    const starts: Extract<AnalysisEvent, { type: "tool_start" }>[] = [];
    const toolCalls: AnalysisTrace["tool_calls"] = [];
    for (const e of events) {
      if (e.type === "tool_start") starts.push(e);
      else if (e.type === "tool_end") {
        const s = starts.pop();
        toolCalls.push({
          id: String(toolCalls.length),
          tool: e.tool ?? s?.tool ?? "tool",
          input: s?.input ?? null,
          output: e.result ?? null,
          status: e.result?.error ? "error" : "success",
          duration_ms: 0,
          ts_ms: 0,
        });
      }
    }
    const end = events.find(
      (e): e is Extract<AnalysisEvent, { type: "agent_end" }> =>
        e.type === "agent_end"
    );
    return {
      run: {
        id: analysisId ?? "",
        analysis_id: analysisId ?? "",
        thread_id: analysisId ?? "",
        status,
        prompt_tokens: end?.prompt_tokens ?? 0,
        completion_tokens: end?.completion_tokens ?? 0,
        cost: 0,
        latency_ms: end?.latency_ms ?? 0,
        tool_calls: toolCalls.length,
        retries: end?.retries ?? 0,
        created_at: null,
        finished_at: null,
      },
      steps,
      tool_calls: toolCalls,
    };
  }

  const traceData = trace ?? buildTrace();
  const st = STATUS_META[status];

  return (
    <section className="card flex h-[72vh] min-h-[520px] flex-col overflow-hidden">
      {/* Tabs */}
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex gap-1 rounded-xl bg-paper-2 p-1">
          {(
            [
              { k: "chat", label: "对话" },
              { k: "report", label: "报告", badge: report ? "✓" : undefined },
              { k: "trace", label: "追踪" },
            ] as { k: Tab; label: string; badge?: string }[]
          ).map((t) => (
            <button
              key={t.k}
              onClick={() => setTab(t.k)}
              className={`flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-semibold transition ${
                tab === t.k
                  ? "bg-surface text-ink shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              {t.label}
              {t.badge && (
                <span className="text-xs text-pine">{t.badge}</span>
              )}
            </button>
          ))}
        </div>
        {status !== "idle" && (
          <span className={`${st.cls} shrink-0`}>
            {status === "running" && (
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber" />
            )}
            {st.label}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1">
        {tab === "chat" && (
          <div className="flex h-full flex-col">
            {/* Selected datasets bar */}
            <div className="flex items-center gap-2 border-b border-line bg-paper-2/40 px-4 py-2">
              <span className="shrink-0 text-xs font-semibold text-muted">
                已选表
              </span>
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                {datasetIds.map((did) => (
                  <span
                    key={did}
                    className="inline-flex max-w-[16rem] items-center gap-1 rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink"
                    title={nameOf(did)}
                  >
                    <span className="truncate">{nameOf(did)}</span>
                    <button
                      type="button"
                      aria-label={`移除 ${nameOf(did)}`}
                      onClick={() =>
                        onRemoveDataset ? onRemoveDataset(did) : undefined
                      }
                      className="text-faint transition hover:text-danger"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setPickerOpen((v) => !v)}
                className="shrink-0 rounded-lg border border-dashed border-line px-2 py-1 text-xs text-muted transition hover:border-accent hover:text-accent-strong"
              >
                + 追加数据集
              </button>
            </div>

            {pickerOpen && (
              <div className="border-b border-line bg-paper-2/40 px-4 py-3">
                <div className="flex flex-wrap gap-1.5">
                  {allDatasets
                    .filter((d) => !datasetIds.includes(d.id))
                    .map((d) => (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => {
                          onAddDataset?.(d.id);
                        }}
                        className="rounded-lg border border-line bg-surface px-2 py-1 text-xs text-muted transition hover:border-accent hover:text-accent-strong"
                      >
                        + {d.name}
                      </button>
                    ))}
                  {allDatasets.filter((d) => !datasetIds.includes(d.id))
                    .length === 0 && (
                    <span className="text-xs text-faint">
                      没有更多可选的数据集。
                    </span>
                  )}
                </div>
              </div>
            )}

            <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
              {events.length === 0 && !loading && (
                <div className="flex h-full flex-col items-center justify-center text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <div className="mt-4 font-display text-lg font-semibold text-ink">
                    想从数据里知道点什么？
                  </div>
                  <p className="mt-1 max-w-sm text-sm text-muted">
                    用自然语言提问，Agent 会自动规划、查询、绘图，并生成报告。
                  </p>
                  <div className="mt-5 flex flex-wrap justify-center gap-2">
                    {EXAMPLES.map((ex) => (
                      <button
                        key={ex}
                        onClick={() => send(ex)}
                        className="tag hover:border-accent hover:text-accent-strong"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {events.map((ev, i) => (
                <EventCard key={i} event={ev} />
              ))}
              {loading && (
                <div className="flex items-center gap-2 px-1 py-2 text-sm text-muted">
                  <span className="flex gap-1">
                    <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.2s]" />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.1s]" />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-accent" />
                  </span>
                  Agent 正在思考…
                </div>
              )}
              {status === "completed" && analysisId && (
                <div className="pt-1">
                  <EvidencePanel analysisId={analysisId} />
                </div>
              )}
            </div>

            {/* Composer */}
            <div className="border-t border-line p-3">
              <button
                type="button"
                onClick={() => setSeedOpen((v) => !v)}
                className="mb-2 flex w-full items-center gap-2 text-xs text-muted transition hover:text-ink"
              >
                <span
                  className={`inline-flex h-4 w-4 items-center justify-center rounded bg-surface-2 text-faint transition-transform duration-200 ${
                    seedOpen ? "rotate-180" : ""
                  }`}
                  aria-hidden
                >
                  ▾
                </span>
                分析侧重
                {seedText.trim() ? (
                  <span className="max-w-[16rem] truncate text-faint">
                    · {seedText.trim()}
                  </span>
                ) : (
                  <span className="text-faint">（可选，随每次提问附加）</span>
                )}
              </button>

              {seedOpen && (
                <textarea
                  className="input mb-2 min-h-[52px] resize-none"
                  value={seedText}
                  onChange={(e) => setSeedText(e.target.value)}
                  placeholder="例如：重点关注用户留存与高价值人群特征"
                />
              )}

              <div className="flex items-end gap-2">
                <textarea
                  className="input min-h-[44px] flex-1 resize-none"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(query);
                      setQuery("");
                    }
                  }}
                  placeholder="描述你的问题，例如：上季度各渠道的转化情况"
                  rows={1}
                />
                <button
                  className="btn btn-primary h-[44px]"
                  onClick={() => {
                    send(query);
                    setQuery("");
                  }}
                  disabled={loading || !query.trim()}
                >
                  发送
                </button>
              </div>
              <div className="mt-1.5 px-1 text-xs text-faint">
                Enter 发送 · Shift+Enter 换行
              </div>
            </div>
          </div>
        )}

        {tab === "report" && (
          <div className="h-full overflow-auto p-5">
            {report ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="eyebrow">AI 生成的分析报告</div>
                  <div className="flex flex-wrap gap-2">
                    <a
                      className="btn btn-quiet"
                      href={reportExportUrl(analysisId!, true)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      打印 / PDF
                    </a>
                    <button
                      className="btn btn-ghost"
                      onClick={() => downloadReport(analysisId!, "insightflow-report.html")}
                      title="下载证据驱动报告（HTML）"
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 3v12m-4-4 4 4 4-4M5 21h14" />
                      </svg>
                      下载 HTML
                    </button>
                    <button
                      className="btn btn-ghost"
                      onClick={() => downloadReportMarkdown(analysisId!)}
                      title="下载证据驱动报告（Markdown，可导入 Notion / Word）"
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
                        <path d="M14 2v6h6" />
                      </svg>
                      下载 Markdown
                    </button>
                  </div>
                </div>
                <AnalysisReportView report={report} />
              </div>
            ) : reportLoading ? (
              <ReportSkeleton />
            ) : reportAttempted && reportError ? (
              <ReportError
                message={reportError}
                onRetry={() => generateReport(analysisId)}
              />
            ) : reportAttempted ? (
              <ReportEmpty onGenerate={() => generateReport(analysisId)} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                正在准备报告…
              </div>
            )}
          </div>
        )}

        {tab === "trace" && (
          <div className="h-full overflow-auto p-5">
            {traceData ? (
              <AgentTrace trace={traceData} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                运行一次分析后，这里会展示 Agent 的执行轨迹与开销。
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function ReportSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted">
        <span className="flex gap-1">
          <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.2s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.1s]" />
          <span className="h-2 w-2 animate-bounce rounded-full bg-accent" />
        </span>
        AI 正在撰写报告，通常只需十几秒…
      </div>
      <div className="skeleton h-8 w-1/2" />
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="skeleton h-20" />
        <div className="skeleton h-20" />
        <div className="skeleton h-20" />
      </div>
      <div className="skeleton h-40" />
      <div className="skeleton h-32" />
    </div>
  );
}

function ReportError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-danger-soft text-danger">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
        </svg>
      </div>
      <div className="font-display text-base font-semibold text-ink">
        报告生成失败
      </div>
      <p className="max-w-sm text-sm text-muted">{message}</p>
      <button className="btn btn-primary" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}

function ReportEmpty({ onGenerate }: { onGenerate: () => void }) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h6" />
        </svg>
      </div>
      <div className="font-display text-base font-semibold text-ink">
        还没有报告
      </div>
      <p className="max-w-sm text-sm text-muted">
        让 AI 基于本次分析结果撰写一份带图表、证据与建议的报告。
      </p>
      <button className="btn btn-primary" onClick={onGenerate}>
        生成报告
      </button>
    </div>
  );
}

function metaFor(type: AnalysisEvent["type"]): {
  label: string;
  cls: string;
  bar: string;
} {
  switch (type) {
    case "message":
    case "agent_end":
      return {
        label: "InsightFlow",
        cls: "border-accent-soft bg-accent-soft/40",
        bar: "bg-accent",
      };
    case "tool_start":
    case "tool_end":
      return {
        label: "工具调用",
        cls: "border-pine-soft bg-pine-soft/40",
        bar: "bg-pine",
      };
    case "error":
      return {
        label: "出错",
        cls: "border-danger-soft bg-danger-soft/50",
        bar: "bg-danger",
      };
    default:
      return { label: "执行", cls: "border-line bg-surface-2", bar: "bg-faint" };
  }
}

export function EventCard({ event }: { event: AnalysisEvent }) {
  const meta = metaFor(event.type);

  // Conversational / prose events render as markdown; structured & data
  // events (tool calls, errors, status) stay as plain monospace text.
  const md =
    event.type === "message"
      ? event.content ?? ""
      : event.type === "agent_end"
      ? event.answer ?? event.content ?? ""
      : event.type === "agent_activity"
      ? event.content ?? ""
      : null;

  return (
    <div className={`fade-up rounded-2xl border p-4 ${meta.cls}`}>
      <div className="mb-1.5 flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${meta.bar}`} />
        <span className="text-xs font-semibold text-ink-soft">{meta.label}</span>
        <span className="tag !py-0.5 !text-[11px]">{event.type}</span>
      </div>
      {md !== null ? (
        <Markdown content={md} className="text-sm leading-relaxed text-ink-soft" />
      ) : (
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">
          {formatEvent(event)}
        </div>
      )}
    </div>
  );
}

function formatEvent(event: AnalysisEvent): string {
  switch (event.type) {
    case "agent_start":
      return `▶ ${event.agent ?? "Agent"} 开始`;
    case "agent_activity":
      return event.content ?? (event.agent ? `${event.agent} 执行中` : "执行中");
    case "tool_start":
      return event.input?.sql || event.input?.code
        ? `🔧 ${event.tool ?? "tool"}\n${event.input.sql ?? event.input.code}`
        : `🔧 ${event.tool ?? "tool"}`;
    case "tool_end":
      return event.result?.error
        ? `⚠ ${event.tool ?? "tool"} 失败：${event.result.error}`
        : `🔧 ${event.tool ?? "tool"} 完成`;
    case "message":
      return event.content ?? "";
    case "agent_end":
      return event.answer ?? event.content ?? "";
    case "error":
      return event.message ?? "分析出错";
    case "chart":
      return `📊 已生成图表：${event.spec.title ?? event.spec.type}`;
    default:
      return "";
  }
}

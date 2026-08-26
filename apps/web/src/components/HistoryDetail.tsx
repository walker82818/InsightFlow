"use client";

import { useState } from "react";
import type {
  AnalysisDetail,
  AnalysisReport,
  AnalysisTrace,
} from "@/types/analysis";
import { EventCard } from "@/components/AnalysisChat";
import AnalysisReportView from "@/components/AnalysisReport";
import AgentTrace from "@/components/AgentTrace";
import { buildReplayEvents } from "@/lib/replay";

const STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  error: "失败",
  running: "分析中",
  pending: "排队中",
};

type SectionKey = "chat" | "report" | "trace";

const SECTIONS: { key: SectionKey; label: string }[] = [
  { key: "chat", label: "对话" },
  { key: "report", label: "报告" },
  { key: "trace", label: "追踪" },
];

export interface HistoryPayload {
  detail: AnalysisDetail;
  report: AnalysisReport | null;
  trace: AnalysisTrace | null;
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-faint">
      {text}
    </div>
  );
}

export default function HistoryDetail({
  payload,
  onBack,
}: {
  payload: HistoryPayload;
  onBack: () => void;
}) {
  const [visible, setVisible] = useState<Record<SectionKey, boolean>>({
    chat: true,
    report: true,
    trace: false,
  });

  const { detail, report, trace } = payload;
  const chatEvents = buildReplayEvents(detail.result);

  return (
    <div className="space-y-5">
      {/* 顶部：标题 + 返回 + 区块勾选 */}
      <section className="card fade-up p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="eyebrow">历史分析 · {STATUS_LABEL[detail.status] ?? detail.status}</div>
            <h1 className="mt-1 truncate font-display text-xl font-bold tracking-tight text-ink">
              {detail.query}
            </h1>
          </div>
          <button className="btn btn-ghost shrink-0" onClick={onBack}>
            ← 返回分析对话
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-faint">显示：</span>
          {SECTIONS.map((s) => {
            const on = visible[s.key];
            const available =
              s.key === "chat"
                ? chatEvents.length > 0
                : s.key === "report"
                  ? !!report
                  : !!trace;
            return (
              <button
                key={s.key}
                onClick={() =>
                  setVisible((v) => ({ ...v, [s.key]: !v[s.key] }))
                }
                disabled={!available}
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition ${
                  on
                    ? "border-accent bg-accent-soft/50 text-ink"
                    : "border-line text-faint hover:border-line-strong"
                } ${!available ? "cursor-not-allowed opacity-50" : ""}`}
                title={available ? "" : "该分析暂无此内容"}
              >
                <span
                  className={`flex h-3.5 w-3.5 items-center justify-center rounded-[5px] border text-[9px] ${
                    on ? "border-accent bg-accent text-paper" : "border-line-strong"
                  }`}
                >
                  {on ? "✓" : ""}
                </span>
                {s.label}
              </button>
            );
          })}
        </div>
      </section>

      {/* 对话 */}
      {visible.chat && (
        <section className="card p-5">
          <div className="eyebrow mb-3">对话</div>
          {chatEvents.length === 0 ? (
            <EmptyState text="该分析暂无对话内容。" />
          ) : (
            <div className="space-y-3">
              {chatEvents.map((ev, i) => (
                <EventCard key={i} event={ev} />
              ))}
            </div>
          )}
        </section>
      )}

      {/* 报告 */}
      {visible.report && (
        <section className="card p-5">
          <div className="eyebrow mb-3">报告</div>
          {report ? (
            <AnalysisReportView report={report} />
          ) : (
            <EmptyState text="该分析暂无报告，可回到对话重新生成。" />
          )}
        </section>
      )}

      {/* 追踪 */}
      {visible.trace && (
        <section className="card p-5">
          <div className="eyebrow mb-3">追踪</div>
          {trace ? (
            <AgentTrace trace={trace} />
          ) : (
            <EmptyState text="该分析暂无追踪记录。" />
          )}
        </section>
      )}

      {!visible.chat && !visible.report && !visible.trace && (
        <p className="text-center text-sm text-faint">
          请至少勾选一个要显示的内容（对话 / 报告 / 追踪）。
        </p>
      )}
    </div>
  );
}

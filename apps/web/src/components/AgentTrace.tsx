"use client";

import type { AgentTraceStep, AnalysisTrace } from "@/types/analysis";

const AGENT_LABELS: Record<string, string> = {
  planner: "规划",
  analysis: "分析",
  visualization: "可视化",
  reviewer: "审查",
  system: "系统",
};

const AGENT_COLORS: Record<string, string> = {
  planner: "bg-accent",
  analysis: "bg-pine",
  visualization: "bg-amber",
  reviewer: "bg-ink-soft",
  system: "bg-faint",
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 font-display text-lg font-bold text-ink">{value}</div>
    </div>
  );
}

function short(value: unknown): string {
  try {
    const s = typeof value === "string" ? value : JSON.stringify(value);
    return s.length > 600 ? s.slice(0, 600) + "…" : s;
  } catch {
    return String(value);
  }
}

function TimelineItem({ step }: { step: AgentTraceStep }) {
  const color = AGENT_COLORS[step.agent] ?? "bg-faint";
  const label = AGENT_LABELS[step.agent] ?? step.agent;
  const isError = step.status === "error";
  return (
    <li className="relative">
      <span
        className={`absolute -left-[1.4rem] top-1 h-3 w-3 rounded-full ring-2 ring-paper ${color}`}
      />
      <div
        className={`rounded-xl border p-3 ${
          isError ? "border-danger-soft bg-danger-soft/40" : "border-line bg-surface"
        }`}
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-semibold text-ink">{label}</span>
            <span className="tag !py-0.5 !text-[11px]">{step.step_type}</span>
          </div>
          {step.duration_ms > 0 && (
            <span className="text-xs text-faint">{step.duration_ms} ms</span>
          )}
        </div>
        {step.content && (
          <div className="text-sm leading-relaxed text-ink-soft">{step.content}</div>
        )}
        {step.step_type === "tool" && step.input != null && (
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-ink px-3 py-2 text-xs text-paper/90">
            {short(step.input)}
          </pre>
        )}
        {step.step_type === "tool" && step.output != null && (
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-2 p-2 text-xs text-ink-soft">
            {short(step.output)}
          </pre>
        )}
      </div>
    </li>
  );
}

export default function AgentTrace({ trace }: { trace: AnalysisTrace }) {
  const { run, steps, tool_calls } = trace;
  const totalTokens = run.prompt_tokens + run.completion_tokens;
  const latencyS = (run.latency_ms / 1000).toFixed(2);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Token 总量" value={totalTokens.toLocaleString()} />
        <Stat label="耗时" value={`${latencyS}s`} />
        <Stat label="工具调用" value={String(tool_calls.length)} />
        <Stat label="重试次数" value={String(run.retries)} />
        <Stat label="提示 Token" value={run.prompt_tokens.toLocaleString()} />
        <Stat label="生成 Token" value={run.completion_tokens.toLocaleString()} />
        <Stat label="预估费用" value={`$${run.cost.toFixed(5)}`} />
        <Stat label="状态" value={run.status} />
      </div>

      <div className="card p-4">
        <div className="mb-3 text-sm font-semibold text-ink">执行时间线</div>
        {steps.length === 0 ? (
          <p className="text-sm text-muted">暂无步骤记录。</p>
        ) : (
          <ol className="relative space-y-4 border-l border-line pl-6">
            {steps.map((s) => (
              <TimelineItem key={s.id} step={s} />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

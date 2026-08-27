"use client";

import { useEffect, useState } from "react";
import {
  getAnalysisEvidences,
  getAnalysisRootCause,
  getEvidenceGraph,
  errMsg,
} from "@/lib/api";
import type {
  EvidenceGraphResponse,
  EvidencesResponse,
  RootCauseResponse,
} from "@/lib/api";

function fmt(n: number): string {
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}

function fmtPct(n: number): string {
  return (n * 100).toFixed(1) + "%";
}

export default function EvidencePanel({
  analysisId,
}: {
  analysisId: string | null;
}) {
  const [evidences, setEvidences] = useState<EvidencesResponse | null>(null);
  const [rootCause, setRootCause] = useState<RootCauseResponse | null>(null);
  const [graph, setGraph] = useState<EvidenceGraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [showGraph, setShowGraph] = useState(false);

  useEffect(() => {
    if (!analysisId) return;
    let cancelled = false;
    (async () => {
      try {
        const [ev, rc, gr] = await Promise.all([
          getAnalysisEvidences(analysisId),
          getAnalysisRootCause(analysisId),
          getEvidenceGraph(analysisId).catch(() => null),
        ]);
        if (cancelled) return;
        setEvidences(ev);
        setRootCause(rc);
        setGraph(gr);
      } catch (e) {
        if (!cancelled) setError(errMsg(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  if (error) return null;
  const rc = rootCause?.root_cause;
  const rows = evidences?.evidences ?? [];
  if (!rc && rows.length === 0) return null;

  return (
    <div className="fade-up space-y-3">
      {/* Root cause */}
      {rc && (
        <div className="rounded-2xl border border-line bg-surface-2 p-4">
          <div className="flex items-center justify-between">
            <div className="eyebrow">根因分解</div>
            {rc.change.significant && (
              <span className="tag tag-amber">阶段变化 {rc.change.reason}</span>
            )}
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">
            {rc.conclusion}
          </p>
          <div className="mt-3">
            <div className="mb-1 flex items-center justify-between text-xs text-faint">
              <span>各因素对 {rc.change.metric} 变化量的贡献</span>
              <span className="font-mono">
                {fmt(rc.change.delta)}（{fmt(rc.change.base_value)} →{" "}
                {fmt(rc.change.current_value)}）
              </span>
            </div>
            <div className="space-y-1.5">
              {rc.contributions.map((c) => {
                const width = Math.max(
                  2,
                  Math.min(100, Math.abs(c.contribution_pct) * 100)
                );
                const pos = c.contribution_pct >= 0;
                return (
                  <div key={c.factor} className="flex items-center gap-2">
                    <span className="w-16 shrink-0 truncate text-xs text-muted">
                      {c.factor}
                    </span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-paper-2">
                      <div
                        className={`h-full rounded-full ${
                          pos ? "bg-pine" : "bg-danger"
                        }`}
                        style={{ width: `${width}%` }}
                      />
                    </div>
                    <span className="w-16 shrink-0 text-right font-mono text-xs text-faint">
                      {pos ? "+" : ""}
                      {fmtPct(c.contribution_pct)}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="mt-2 text-[10px] text-faint">
              置信 {Math.round(rc.confidence * 100)}%
            </div>
          </div>
          {rc.hypotheses.length > 0 && (
            <div className="mt-3 border-t border-line pt-3">
              <div className="mb-1.5 text-xs text-faint">候选假设</div>
              <ul className="space-y-1">
                {rc.hypotheses.map((h, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 rounded-xl bg-surface px-3 py-2 text-xs"
                  >
                    <span
                      className={`tag mt-0.5 shrink-0 !py-0 !text-[10px] ${
                        h.status === "已证实" ? "tag-pine" : "tag-amber"
                      }`}
                    >
                      {h.status}
                    </span>
                    <span className="text-ink-soft">{h.hypothesis}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Evidence chain */}
      {rows.length > 0 && (
        <div className="rounded-2xl border border-line bg-surface-2 p-4">
          <div className="flex items-center justify-between">
            <div className="eyebrow">证据链</div>
            <div className="flex items-center gap-2">
              {graph && graph.edges.length > 0 && (
                <button
                  className="text-xs text-accent hover:text-accent-strong"
                  onClick={() => setShowGraph((v) => !v)}
                >
                  {showGraph ? "收起图谱" : "证据图谱"}
                </button>
              )}
              <button
                className="text-xs text-accent hover:text-accent-strong"
                onClick={() => setShowAll((v) => !v)}
              >
                {showAll ? "收起" : `展开全部 ${rows.length} 条`}
              </button>
            </div>
          </div>

          {showGraph && graph && <EvidenceGraphView graph={graph} />}

          <div className="mt-2 space-y-2">
            {(showAll ? rows : rows.slice(0, 3)).map((ev) => (
              <div
                key={ev.id}
                className="rounded-xl border border-line bg-surface px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
                      ev.source === "sql"
                        ? "bg-pine-soft text-pine-strong"
                        : "bg-accent-soft text-accent-strong"
                    }`}
                  >
                    {ev.source === "sql" ? "SQL" : "Python"}
                  </span>
                  <span className="truncate text-xs text-ink-soft">
                    {ev.claim || "（无摘要）"}
                  </span>
                  <span className="ml-auto shrink-0 font-mono text-[10px] text-faint">
                    置信 {Math.round(ev.confidence * 100)}%
                  </span>
                </div>
                {ev.sql && (
                  <pre className="mt-1.5 overflow-x-auto rounded-md bg-paper-2 px-2 py-1.5 font-mono text-[10px] leading-relaxed text-faint">
                    {ev.sql}
                  </pre>
                )}
                {ev.result?.rows && (
                  <div className="mt-1.5 text-[10px] text-faint">
                    {ev.result.row_count} 行 × {String(ev.result.columns?.length)} 列
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  sql: "SQL",
  python: "Python",
  llm_reasoning: "推理",
  semantic: "语义",
  profile: "画像",
};

function EvidenceGraphView({ graph }: { graph: EvidenceGraphResponse }) {
  const nodes = graph.nodes;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const children = new Map<string, typeof nodes>();
  const roots: typeof nodes = [];
  for (const e of graph.edges) {
    const list = children.get(e.from) ?? [];
    list.push(byId.get(e.to)!);
    children.set(e.from, list);
  }
  for (const n of nodes) {
    if (!n.parent_id || !byId.has(n.parent_id)) roots.push(n);
  }
  const renderNode = (n: (typeof nodes)[number], depth: number) => (
    <div key={n.id} className="flex items-start gap-2">
      <div className="flex w-5 shrink-0 justify-end pt-1 text-faint">
        {Array.from({ length: depth }).map((_, i) => (
          <span key={i} className="inline-block w-2">
            │
          </span>
        ))}
        {depth > 0 && <span className="text-accent">└</span>}
      </div>
      <div className="min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 py-2">
        <div className="flex items-center gap-2">
          <span
            className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
              n.source === "sql"
                ? "bg-pine-soft text-pine"
                : n.source === "llm_reasoning"
                ? "bg-accent-soft text-accent-strong"
                : "bg-paper-2 text-muted"
            }`}
          >
            {SOURCE_LABEL[n.source] ?? n.source}
          </span>
          <span className="truncate text-xs text-ink-soft">{n.claim || "（无摘要）"}</span>
          <span className="ml-auto shrink-0 font-mono text-[10px] text-faint">
            置信 {Math.round(n.confidence * 100)}%
          </span>
        </div>
        {(children.get(n.id) ?? []).length > 0 && (
          <div className="mt-2 space-y-1.5">
            {(children.get(n.id) ?? []).map((c) => renderNode(c, depth + 1))}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="mt-3 space-y-1.5">
      <div className="text-[10px] text-faint">
        多跳溯源 · {nodes.length} 节点 / {graph.edges.length} 条溯源
      </div>
      {roots.length === 0 && (
        <div className="rounded-xl bg-surface px-3 py-2 text-xs text-muted">
          暂无可回溯的证据链
        </div>
      )}
      {roots.map((r) => renderNode(r, 0))}
    </div>
  );
}

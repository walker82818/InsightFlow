import type { ArtifactSpec } from "@insightflow/artifact-schema";
import type { AnalysisEvent } from "@/types/analysis";

/**
 * Reconstruct a read-only event stream from a persisted analysis result so a
 * past analysis can be replayed in the chat view (Phase 6 history review).
 */
export function buildReplayEvents(
  result: Record<string, unknown>,
): AnalysisEvent[] {
  const evs: AnalysisEvent[] = [];
  const plan = (result.plan as string[]) ?? [];
  const steps = (result.steps as Array<Record<string, unknown>>) ?? [];
  const viz = (result.visualizations as ArtifactSpec[]) ?? [];
  const answer = (result.answer as string) ?? "";

  evs.push({
    type: "agent_activity",
    agent: "planner",
    content: "规划完成",
    status: "done",
  });
  plan.forEach((p) => evs.push({ type: "message", content: String(p) }));
  steps.forEach((s) => {
    const tool = s.tool as string | undefined;
    if (tool === "sql_execute") {
      evs.push({
        type: "tool_start",
        tool: "sql_execute",
        input: { sql: (s.sql as string) ?? "" },
      });
      evs.push({
        type: "tool_end",
        tool: "sql_execute",
        result: s.result as never,
      });
    } else if (tool === "python_execute") {
      evs.push({
        type: "tool_start",
        tool: "python_execute",
        input: { code: (s.code as string) ?? "" },
      });
      evs.push({
        type: "tool_end",
        tool: "python_execute",
        result: s.result as never,
      });
    }
  });
  viz.forEach((spec) => evs.push({ type: "chart", spec }));
  if (answer) evs.push({ type: "message", content: answer });
  evs.push({ type: "agent_end", status: "completed" });
  return evs;
}

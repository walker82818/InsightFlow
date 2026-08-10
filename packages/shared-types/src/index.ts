import type { ChartSpec } from "@insightflow/chart-schema";

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  llmProvider: string;
}

export interface HealthDbResponse {
  status: string;
  database: string;
  detail?: string;
}

// SSE agent event stream — frontend consumes these to render live Agent state.
export type AgentEvent =
  | { type: "agent_start"; agent: string }
  | { type: "agent_end"; agent: string }
  | { type: "tool_start"; tool: string }
  | { type: "tool_end"; tool: string; result: unknown }
  | { type: "message"; content: string }
  | { type: "chart"; spec: ChartSpec }
  | { type: "interrupt"; payload: unknown }
  | { type: "error"; message: string };

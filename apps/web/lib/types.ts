// Mirrors the API's Pydantic models (services/api/app/agent/answer.py) and the chat events
// (services/api/app/routes.py). Field names stay snake_case to match the JSON exactly.

export type Cell = string | number | boolean | null;

export interface Table {
  result_id: string;
  columns: string[];
  rows: Cell[][];
}

export interface Chart {
  type: "bar" | "line";
  x: string;
  y: string;
}

export interface Citation {
  chunk_id: string;
  doc_title: string;
  section: string;
  source: string;
}

export interface SqlEvidence {
  result_id: string;
  tool: string;
  sql: string;
  params?: Record<string, unknown> | null;
}

export interface Denial {
  result_id: string;
  tool: string;
  denied_by: string;
  message: string;
}

export interface Answer {
  text: string;
  assumptions?: string[];
  table?: Table | null;
  chart?: Chart | null;
  citations?: Citation[];
  sql?: SqlEvidence[];
  denials?: Denial[];
  issues?: string[];
}

export interface Usage {
  model_calls?: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  cost_usd?: number;
  latency_ms?: number;
}

export type Mode = "live" | "cached" | "replay" | "limited";

export interface ToolResultSummary {
  result_id: string;
  tool: string;
  status: "ok" | "denied" | "error";
  row_count?: number | null;
  columns?: string[] | null;
  denied_by?: string | null;
  message?: string | null;
  duration_ms?: number;
}

export type ChatEvent =
  | { type: "mode"; data: { mode: Mode; reason: string | null } }
  | { type: "trace_id"; data: { trace_id: string } }
  | { type: "step"; data: { step: string; label?: string; category?: string } }
  | { type: "tool_call"; data: { tool: string; input: Record<string, unknown> } }
  | { type: "tool_result"; data: ToolResultSummary }
  | { type: "answer"; data: Answer }
  | { type: "usage"; data: Usage }
  | { type: "error"; data: { message: string } };

export interface Persona {
  id: string;
  name: string;
  title: string;
  location: string;
  region: string | null;
  role: string;
}

export interface Sample {
  id: string;
  persona: string;
  question: string;
  answer: Answer | null;
  usage: Usage | null;
}

export interface Preset extends Sample {
  category: "access_control" | "robustness";
  eval_file: string;
}

export interface DemoData {
  personas: Persona[];
  samples: Sample[];
  presets: Preset[];
}

import type { Answer, ChatEvent, Mode, ToolResultSummary, Usage } from "./types";

export interface Step {
  key: string;
  label: string;
  detail?: string;
  status: "done" | "denied" | "error" | "running";
}

export interface Turn {
  question: string;
  status: "streaming" | "done" | "error";
  mode: Mode | null;
  modeReason: string | null;
  steps: Step[];
  answer: Answer | null;
  usage: Usage | null;
  traceId: string | null;
  error: string | null;
}

export function newTurn(question: string): Turn {
  return {
    question,
    status: "streaming",
    mode: null,
    modeReason: null,
    steps: [],
    answer: null,
    usage: null,
    traceId: null,
    error: null,
  };
}

/** A finished turn from a precomputed answer (sample questions, preset replays). */
export function cachedTurn(question: string, answer: Answer, usage: Usage | null): Turn {
  return {
    ...newTurn(question),
    status: "done",
    mode: "cached",
    steps: stepsFromEvidence(answer),
    answer,
    usage,
  };
}

const TOOL_LABELS: Record<string, string> = {
  get_metric: "Queried a governed metric",
  run_sql: "Ran a read-only SQL query",
  search_documents: "Searched policy documents",
  describe_tables: "Looked up table columns",
  list_metrics: "Listed available metrics",
};

const GUARD_LABELS: Record<string, string> = {
  in_scope: "Question is in scope",
  out_of_scope: "Out of scope: declined before any data access",
  injection_suspected: "Possible prompt injection: answering only within this role",
};

function toolStep(result: ToolResultSummary): Step {
  const label = TOOL_LABELS[result.tool] ?? result.tool;
  if (result.status === "denied") {
    return {
      key: result.result_id,
      label,
      status: "denied",
      detail: `Blocked by ${result.denied_by ?? "access control"}`,
    };
  }
  if (result.status === "error") {
    return { key: result.result_id, label, status: "error", detail: result.message ?? undefined };
  }
  const rows = result.row_count ?? 0;
  const timing = result.duration_ms !== undefined ? ` in ${result.duration_ms} ms` : "";
  return {
    key: result.result_id,
    label,
    status: "done",
    detail: `${rows} row${rows === 1 ? "" : "s"}${timing}`,
  };
}

/** Rebuild the "How this answer was built" list from a cached answer's evidence. */
export function stepsFromEvidence(answer: Answer): Step[] {
  const steps: Step[] = [];
  for (const sql of answer.sql ?? []) {
    steps.push({
      key: sql.result_id,
      label: TOOL_LABELS[sql.tool] ?? sql.tool,
      status: "done",
    });
  }
  for (const denial of answer.denials ?? []) {
    steps.push({
      key: denial.result_id,
      label: TOOL_LABELS[denial.tool] ?? denial.tool,
      status: "denied",
      detail: `Blocked by ${denial.denied_by}`,
    });
  }
  if ((answer.citations ?? []).length > 0) {
    steps.push({ key: "documents", label: TOOL_LABELS.search_documents, status: "done" });
  }
  steps.sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
  steps.push({ key: "answer", label: "Wrote the answer from those results", status: "done" });
  return steps;
}

export function reduce(turn: Turn, event: ChatEvent): Turn {
  switch (event.type) {
    case "mode":
      return { ...turn, mode: event.data.mode, modeReason: event.data.reason };
    case "trace_id":
      return { ...turn, traceId: event.data.trace_id };
    case "step": {
      if (event.data.step === "guard_result") {
        const category = event.data.category ?? "in_scope";
        const steps = finishRunning(turn.steps).map((s) =>
          s.key === "guard" ? { ...s, label: GUARD_LABELS[category] ?? s.label } : s,
        );
        return { ...turn, steps };
      }
      const step: Step = {
        key: event.data.step,
        label: event.data.label ?? event.data.step,
        status: "running",
      };
      return { ...turn, steps: [...finishRunning(turn.steps), step] };
    }
    case "tool_call":
      return {
        ...turn,
        steps: [
          ...finishRunning(turn.steps),
          {
            key: `call-${turn.steps.length}`,
            label: TOOL_LABELS[event.data.tool] ?? event.data.tool,
            status: "running",
          },
        ],
      };
    case "tool_result": {
      const steps = [...turn.steps];
      const index = steps.findLastIndex((s) => s.status === "running");
      const step = toolStep(event.data);
      if (index === -1) steps.push(step);
      else steps[index] = step;
      return { ...turn, steps };
    }
    case "answer":
      return { ...turn, answer: event.data, steps: finishRunning(turn.steps) };
    case "usage":
      return { ...turn, usage: event.data, status: "done" };
    case "error":
      return { ...turn, error: event.data.message, status: "error" };
  }
}

function finishRunning(steps: Step[]): Step[] {
  return steps.map((s) => (s.status === "running" ? { ...s, status: "done" } : s));
}

/** Close a turn whose stream ended without a usage event (replay messages, dropped streams). */
export function finish(turn: Turn): Turn {
  if (turn.status !== "streaming") return turn;
  return { ...turn, status: turn.answer ? "done" : "error", steps: finishRunning(turn.steps) };
}

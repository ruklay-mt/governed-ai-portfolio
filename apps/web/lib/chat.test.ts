import { describe, expect, it } from "vitest";

import { cachedTurn, finish, newTurn, reduce, stepsFromEvidence } from "./chat";
import type { ChatEvent } from "./types";

function play(events: ChatEvent[]) {
  return events.reduce(reduce, newTurn("What was AU-EAST's revenue?"));
}

describe("reduce", () => {
  it("builds steps from a live stream", () => {
    const turn = play([
      { type: "mode", data: { mode: "live", reason: null } },
      { type: "step", data: { step: "guard", label: "Checking the question" } },
      { type: "step", data: { step: "guard_result", category: "in_scope" } },
      { type: "tool_call", data: { tool: "get_metric", input: {} } },
      {
        type: "tool_result",
        data: { result_id: "r1", tool: "get_metric", status: "ok", row_count: 1, duration_ms: 120 },
      },
      { type: "step", data: { step: "answer", label: "Writing the answer" } },
      { type: "answer", data: { text: "NZD 1.2m." } },
      { type: "usage", data: { cost_usd: 0.012, latency_ms: 6000 } },
    ]);
    expect(turn.status).toBe("done");
    expect(turn.mode).toBe("live");
    expect(turn.steps.map((s) => [s.label, s.status])).toEqual([
      ["Question is in scope", "done"],
      ["Queried a governed metric", "done"],
      ["Writing the answer", "done"],
    ]);
    expect(turn.steps[1].detail).toBe("1 row in 120 ms");
    expect(turn.answer?.text).toBe("NZD 1.2m.");
  });

  it("marks a denied tool with the mechanism that blocked it", () => {
    const turn = play([
      { type: "tool_call", data: { tool: "run_sql", input: {} } },
      {
        type: "tool_result",
        data: {
          result_id: "r1",
          tool: "run_sql",
          status: "denied",
          denied_by: "Postgres column grant",
        },
      },
    ]);
    expect(turn.steps[0]).toMatchObject({ status: "denied", detail: "Blocked by Postgres column grant" });
  });

  it("records errors", () => {
    const turn = play([{ type: "error", data: { message: "model call failed" } }]);
    expect(turn.status).toBe("error");
    expect(turn.error).toBe("model call failed");
  });
});

describe("finish", () => {
  it("closes a replay stream that has an answer but no usage", () => {
    const turn = finish(
      play([
        { type: "mode", data: { mode: "replay", reason: "daily budget reached" } },
        { type: "answer", data: { text: "Live answers are paused." } },
      ]),
    );
    expect(turn.status).toBe("done");
    expect(turn.modeReason).toBe("daily budget reached");
  });

  it("treats a stream with no answer as an error", () => {
    expect(finish(newTurn("q")).status).toBe("error");
  });
});

describe("stepsFromEvidence", () => {
  it("lists queries, denials and documents in result order", () => {
    const steps = stepsFromEvidence({
      text: "x",
      sql: [{ result_id: "r2", tool: "get_metric", sql: "select 1" }],
      denials: [{ result_id: "r1", tool: "get_metric", denied_by: "semantic layer role check", message: "" }],
      citations: [{ chunk_id: "c1", doc_title: "Pricing", section: "Discounts", source: "pricing.md" }],
    });
    expect(steps.map((s) => s.status)).toEqual(["done", "denied", "done", "done"]);
    expect(steps.at(-1)?.key).toBe("answer");
  });

  it("gives cached turns a cached mode", () => {
    expect(cachedTurn("q", { text: "a" }, null).mode).toBe("cached");
  });
});

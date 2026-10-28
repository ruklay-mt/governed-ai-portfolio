import { describe, expect, it } from "vitest";

import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses complete events", () => {
    const parser = new SseParser();
    const events = parser.push(
      'event: mode\ndata: {"mode": "live", "reason": null}\n\nevent: usage\ndata: {"cost_usd": 0.01}\n\n',
    );
    expect(events).toEqual([
      { type: "mode", data: { mode: "live", reason: null } },
      { type: "usage", data: { cost_usd: 0.01 } },
    ]);
  });

  it("buffers an event split across chunks", () => {
    const parser = new SseParser();
    expect(parser.push('event: answer\ndata: {"te')).toEqual([]);
    expect(parser.push('xt": "Hi"}\n')).toEqual([]);
    expect(parser.push("\n")).toEqual([{ type: "answer", data: { text: "Hi" } }]);
  });

  it("handles CRLF line endings", () => {
    const parser = new SseParser();
    expect(parser.push('event: error\r\ndata: {"message": "x"}\r\n\r\n')).toEqual([
      { type: "error", data: { message: "x" } },
    ]);
  });

  it("skips unknown events and malformed data", () => {
    const parser = new SseParser();
    expect(parser.push("event: ping\ndata: {}\n\nevent: answer\ndata: {oops\n\n")).toEqual([]);
  });
});

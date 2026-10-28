import type { ChatEvent } from "./types";

const KNOWN = new Set([
  "mode",
  "trace_id",
  "step",
  "tool_call",
  "tool_result",
  "answer",
  "usage",
  "error",
]);

/**
 * Incremental parser for the chat endpoint's server-sent events.
 *
 * The endpoint is a POST, so the browser's EventSource can't be used; we read the fetch body
 * stream instead. Chunks can split an event anywhere, so text is buffered until a blank line.
 */
export class SseParser {
  private buffer = "";

  push(chunk: string): ChatEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: ChatEvent[] = [];
    let end = this.buffer.indexOf("\n\n");
    while (end !== -1) {
      const block = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 2);
      const event = parseBlock(block);
      if (event) events.push(event);
      end = this.buffer.indexOf("\n\n");
    }
    return events;
  }
}

function parseBlock(block: string): ChatEvent | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!KNOWN.has(name) || data.length === 0) return null;
  try {
    return { type: name, data: JSON.parse(data.join("\n")) } as ChatEvent;
  } catch {
    return null;
  }
}

/** POST a question and yield events as they arrive. */
export async function* streamChat(
  url: string,
  body: { persona: string; session_id: string; message: string },
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => "");
    throw new Error(`The assistant returned ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    yield* parser.push(value);
  }
}

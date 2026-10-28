import { describe, expect, it } from "vitest";

import { type ApiState, warmUp } from "./health";

function respond(...bodies: (object | Error)[]): typeof fetch {
  let call = 0;
  return (async () => {
    const body = bodies[Math.min(call++, bodies.length - 1)];
    if (body instanceof Error) throw body;
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
}

describe("warmUp", () => {
  it("is ready once the database answers", async () => {
    const states: ApiState[] = [];
    const fetcher = respond(new Error("cold"), { db: "unavailable" }, { db: "ok" });
    expect(await warmUp("http://api", (s) => states.push(s), fetcher, 5, 0)).toBe("ready");
    expect(states).toEqual(["warming", "ready"]);
  });

  it("gives up after the last attempt", async () => {
    const fetcher = respond(new Error("down"));
    expect(await warmUp("http://api", () => {}, fetcher, 2, 0)).toBe("unavailable");
  });
});

import data from "../data/demo.json";

import type { DemoData } from "./types";

// Built by `make samples-build` / `make samples-export` and imported at build time, so sample
// answers render with no API call (ADR 0013).
export const DEMO = data as DemoData;

export function newSessionId(): string {
  return crypto.randomUUID();
}

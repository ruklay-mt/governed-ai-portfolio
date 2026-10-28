import { describe, expect, it } from "vitest";

import { DEMO } from "./demo";
import { evalCaseUrl } from "./site";

describe("demo data", () => {
  it("has five or more answered samples per persona and answered presets", () => {
    for (const persona of DEMO.personas) {
      const answered = DEMO.samples.filter((s) => s.persona === persona.id && s.answer);
      expect(answered.length).toBeGreaterThanOrEqual(5);
    }
    expect(DEMO.presets.length).toBeGreaterThan(0);
    expect(DEMO.presets.every((p) => p.answer && p.eval_file.startsWith("evals/cases/"))).toBe(true);
  });

  it("links presets to their eval case on GitHub", () => {
    expect(evalCaseUrl("evals/cases/access_control.yml", "ac-x")).toBe(
      "https://github.com/ruklay-mt/governed-ai-portfolio/blob/main/evals/cases/access_control.yml#:~:text=id%3A%20ac-x",
    );
  });
});

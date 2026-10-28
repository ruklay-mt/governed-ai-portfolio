import { describe, expect, it } from "vitest";

import { columnLabel, formatCell, formatCost, formatLatency, totalTokens } from "./format";

describe("format", () => {
  it("formats cost", () => {
    expect(formatCost(0)).toBe("US$0 (cached)");
    expect(formatCost(0.0055)).toBe("US$0.0055");
    expect(formatCost(0.0234)).toBe("US$0.023");
    expect(formatCost(undefined)).toBe("-");
  });

  it("formats latency", () => {
    expect(formatLatency(850)).toBe("850 ms");
    expect(formatLatency(6885)).toBe("6.9 s");
  });

  it("formats cells, including numeric strings from Postgres numerics", () => {
    expect(formatCell(null)).toBe("-");
    expect(formatCell("1234567.891")).toBe("1,234,567.89");
    expect(formatCell("NZ-SOUTH")).toBe("NZ-SOUTH");
  });

  it("labels columns and sums tokens", () => {
    expect(columnLabel("revenue_nzd")).toBe("Revenue nzd");
    expect(totalTokens({ input_tokens: 1, output_tokens: 2, cache_read_tokens: 3 })).toBe(6);
  });
});

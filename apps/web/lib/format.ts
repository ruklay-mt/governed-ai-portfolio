import type { Cell, Usage } from "./types";

export function formatCost(usd: number | undefined): string {
  if (usd === undefined) return "-";
  if (usd === 0) return "US$0 (cached)";
  if (usd < 0.01) return `US$${usd.toFixed(4)}`;
  return `US$${usd.toFixed(3)}`;
}

export function formatLatency(ms: number | undefined): string {
  if (ms === undefined) return "-";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function totalTokens(usage: Usage): number {
  return (
    (usage.input_tokens ?? 0) +
    (usage.output_tokens ?? 0) +
    (usage.cache_read_tokens ?? 0) +
    (usage.cache_write_tokens ?? 0)
  );
}

const NUMBER = new Intl.NumberFormat("en-NZ", { maximumFractionDigits: 2 });

export function formatCell(value: Cell): string {
  if (value === null) return "-";
  if (typeof value === "number") return NUMBER.format(value);
  if (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value)) {
    return NUMBER.format(Number(value));
  }
  return String(value);
}

/** Column names from SQL (snake_case) as table headings. */
export function columnLabel(column: string): string {
  const words = column.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

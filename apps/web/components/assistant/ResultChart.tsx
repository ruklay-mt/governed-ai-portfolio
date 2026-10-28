"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { columnLabel } from "@/lib/format";
import type { Chart, Table } from "@/lib/types";

const COMPACT = new Intl.NumberFormat("en-NZ", { notation: "compact", maximumFractionDigits: 1 });

export function ResultChart({ chart, table }: { chart: Chart; table: Table }) {
  const xi = table.columns.indexOf(chart.x);
  const yi = table.columns.indexOf(chart.y);
  if (xi === -1 || yi === -1) return null;
  const data = table.rows
    .map((row) => ({ x: String(row[xi] ?? ""), y: Number(row[yi]) }))
    .filter((d) => Number.isFinite(d.y));
  if (data.length < 2) return null;

  const axis = { stroke: "var(--muted)", fontSize: 12 };
  const common = (
    <>
      <CartesianGrid stroke="var(--border)" vertical={false} />
      <XAxis dataKey="x" tick={axis} tickLine={false} axisLine={false} />
      <YAxis tick={axis} tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => COMPACT.format(v)} />
      <Tooltip
        formatter={(v) => [COMPACT.format(Number(v)), columnLabel(chart.y)]}
        contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }}
      />
    </>
  );
  return (
    <figure className="h-56 w-full" aria-label={`${columnLabel(chart.y)} by ${columnLabel(chart.x)}`}>
      <ResponsiveContainer width="100%" height="100%">
        {chart.type === "line" ? (
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            {common}
            <Line dataKey="y" stroke="var(--accent)" strokeWidth={2} dot={false} />
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            {common}
            <Bar dataKey="y" fill="var(--accent)" radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </figure>
  );
}

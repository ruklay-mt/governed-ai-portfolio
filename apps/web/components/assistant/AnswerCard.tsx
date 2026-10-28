"use client";

import type { Step, Turn } from "@/lib/chat";
import { columnLabel, formatCell, formatCost, formatLatency, totalTokens } from "@/lib/format";
import type { Answer, Table } from "@/lib/types";

import { ResultChart } from "./ResultChart";

const MODE_LABELS: Record<string, string> = {
  live: "Live",
  cached: "Precomputed",
  replay: "Replay",
  limited: "Rate limited",
};

export function AnswerCard({
  turn,
  personaName,
  evalLink,
}: {
  turn: Turn;
  personaName: string;
  evalLink?: string;
}) {
  const answer = turn.answer;
  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-xl border border-border bg-surface p-4 sm:p-5">
      <header className="flex flex-col gap-1">
        <p className="text-xs text-muted">
          Asked as {personaName}
          {turn.mode ? ` · ${MODE_LABELS[turn.mode] ?? turn.mode}` : ""}
        </p>
        <h3 className="font-medium">{turn.question}</h3>
      </header>

      {turn.status === "streaming" && !answer && <Steps steps={turn.steps} live />}

      {turn.error && (
        <p className="rounded-md border border-danger/40 p-3 text-sm text-danger">
          {turn.error}
        </p>
      )}

      {answer && (
        <>
          <p className="leading-relaxed">{answer.text}</p>
          <Denials answer={answer} />
          {answer.table && answer.table.rows.length > 0 && (
            <>
              {answer.chart && <ResultChart chart={answer.chart} table={answer.table} />}
              <ResultTable table={answer.table} />
            </>
          )}
          <Citations answer={answer} />
          <Evidence answer={answer} turn={turn} />
          <Badges turn={turn} evalLink={evalLink} />
        </>
      )}
    </article>
  );
}

function Denials({ answer }: { answer: Answer }) {
  const denials = answer.denials ?? [];
  if (denials.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-denied/40 bg-denied-soft p-3 text-sm">
      <p className="font-medium text-denied">Access denied, by design</p>
      {denials.map((d) => (
        <p key={d.result_id}>
          <span className="font-medium">{d.denied_by}</span> blocked{" "}
          <code className="font-mono text-xs">{d.tool}</code>:{" "}
          <span className="font-mono text-xs break-words">{d.message}</span>
        </p>
      ))}
      <p className="text-xs text-muted">
        Enforced outside the model: the semantic layer and the database decide what this role
        can see, so a clever prompt can&apos;t talk its way past it.
      </p>
    </div>
  );
}

function ResultTable({ table }: { table: Table }) {
  return (
    <div className="max-h-80 overflow-auto rounded-lg border border-border">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-border">
            {table.columns.map((c) => (
              <th key={c} className="px-3 py-2 font-medium whitespace-nowrap text-muted">
                {columnLabel(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} className="border-b border-border last:border-0">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={`px-3 py-1.5 whitespace-nowrap ${typeof cell === "number" || /^-?\d/.test(String(cell)) ? "text-right tabular-nums" : ""}`}
                >
                  {formatCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Citations({ answer }: { answer: Answer }) {
  const citations = answer.citations ?? [];
  if (citations.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p className="font-medium">Sources</p>
      <ul className="flex flex-col gap-1">
        {citations.map((c) => (
          <li key={c.chunk_id} className="text-muted">
            <span className="text-foreground">{c.doc_title}</span> · {c.section}{" "}
            <span className="font-mono text-xs">({c.source})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Evidence({ answer, turn }: { answer: Answer; turn: Turn }) {
  const sql = answer.sql ?? [];
  const assumptions = answer.assumptions ?? [];
  return (
    <div className="flex flex-col gap-2 text-sm">
      {sql.length > 0 && (
        <details className="group rounded-lg border border-border">
          <summary className="cursor-pointer px-3 py-2 font-medium">Show SQL ({sql.length})</summary>
          <div className="flex flex-col gap-3 border-t border-border p-3">
            {sql.map((s) => (
              <div key={s.result_id} className="flex flex-col gap-1">
                <p className="text-xs text-muted">
                  {s.tool} · {s.result_id}
                  {s.params && Object.keys(s.params).length > 0
                    ? ` · params ${JSON.stringify(s.params)}`
                    : ""}
                </p>
                <pre className="overflow-x-auto rounded-md bg-background p-2 font-mono text-xs leading-relaxed">
                  {s.sql}
                </pre>
              </div>
            ))}
          </div>
        </details>
      )}
      <details className="rounded-lg border border-border">
        <summary className="cursor-pointer px-3 py-2 font-medium">How this answer was built</summary>
        <div className="flex flex-col gap-3 border-t border-border p-3">
          <Steps steps={turn.steps} />
          {assumptions.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted">Assumptions</p>
              <ul className="list-disc pl-5">
                {assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          )}
          {(answer.issues ?? []).length > 0 && (
            <p className="text-xs text-muted">Notes: {(answer.issues ?? []).join("; ")}</p>
          )}
        </div>
      </details>
    </div>
  );
}

const STEP_ICON: Record<Step["status"], string> = {
  done: "✓",
  denied: "⛔",
  error: "!",
  running: "…",
};

function Steps({ steps, live = false }: { steps: Step[]; live?: boolean }) {
  if (steps.length === 0) {
    return <p className="text-sm text-muted">{live ? "Starting…" : "No tools were needed."}</p>;
  }
  return (
    <ol className="flex flex-col gap-1 text-sm" aria-live={live ? "polite" : undefined}>
      {steps.map((s) => (
        <li key={s.key} className="flex gap-2">
          <span
            aria-hidden
            className={`w-4 shrink-0 text-center ${s.status === "denied" ? "text-denied" : s.status === "running" ? "animate-pulse text-muted" : "text-accent"}`}
          >
            {STEP_ICON[s.status]}
          </span>
          <span>
            {s.label}
            {s.detail && <span className="text-muted"> · {s.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Badges({ turn, evalLink }: { turn: Turn; evalLink?: string }) {
  const usage = turn.usage;
  const items: string[] = [];
  if (usage) {
    const latency = formatLatency(usage.latency_ms);
    items.push(turn.mode === "live" ? latency : `${latency} when computed`);
    const tokens = totalTokens(usage);
    if (tokens > 0) items.push(`${tokens.toLocaleString("en-NZ")} tokens`);
    items.push(turn.mode === "live" ? formatCost(usage.cost_usd) : "US$0 now (precomputed)");
  }
  return (
    <footer className="flex flex-wrap items-center gap-2 text-xs text-muted">
      {items.map((item) => (
        <span key={item} className="rounded-full border border-border px-2 py-0.5">
          {item}
        </span>
      ))}
      {evalLink && (
        <a href={evalLink} className="text-accent underline-offset-2 hover:underline" target="_blank" rel="noreferrer">
          This attack is an eval case in CI ↗
        </a>
      )}
    </footer>
  );
}

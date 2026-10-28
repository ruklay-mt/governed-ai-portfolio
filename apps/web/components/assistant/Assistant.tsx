"use client";

import { useEffect, useRef, useState } from "react";

import { cachedTurn, finish, newTurn, reduce, type Turn } from "@/lib/chat";
import { apiBaseUrl } from "@/lib/env";
import { type ApiState, warmUp } from "@/lib/health";
import { evalCaseUrl } from "@/lib/site";
import { streamChat } from "@/lib/sse";
import type { DemoData, Persona, Preset } from "@/lib/types";

import { AnswerCard } from "./AnswerCard";

interface Entry {
  id: number;
  persona: Persona;
  turn: Turn;
  preset?: Preset;
}

const MAX_QUESTION = 500;

const API_STATE_TEXT: Record<ApiState, string> = {
  unknown: "",
  warming: "Waking the live assistant (servers scale to zero). Sample questions work right away.",
  ready: "Live assistant ready.",
  unavailable: "The live assistant isn't responding. Sample questions and attack replays still work.",
};

export function Assistant({ demo }: { demo: DemoData }) {
  const [personaId, setPersonaId] = useState(demo.personas[0].id);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [apiState, setApiState] = useState<ApiState>("unknown");
  const sessionId = useRef<string | null>(null);
  const nextId = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);

  const persona = demo.personas.find((p) => p.id === personaId) ?? demo.personas[0];
  const samples = demo.samples.filter((s) => s.persona === persona.id);

  useEffect(() => {
    void warmUp(apiBaseUrl(), setApiState);
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries.length]);

  function add(entry: Omit<Entry, "id">): number {
    const id = nextId.current++;
    setEntries((current) => [...current, { ...entry, id }]);
    return id;
  }

  function update(id: number, change: (turn: Turn) => Turn) {
    setEntries((current) => current.map((e) => (e.id === id ? { ...e, turn: change(e.turn) } : e)));
  }

  async function askLive(text: string, who: Persona, preset?: Preset) {
    const id = add({ persona: who, turn: newTurn(text), preset });
    setBusy(true);
    sessionId.current ??= crypto.randomUUID();
    try {
      const events = streamChat(`${apiBaseUrl()}/api/chat`, {
        persona: who.id,
        session_id: sessionId.current,
        message: text,
      });
      for await (const event of events) update(id, (turn) => reduce(turn, event));
      update(id, finish);
    } catch (error) {
      if (preset?.answer) {
        // The API is down or cold: show the precomputed refusal rather than an error.
        update(id, () => ({
          ...cachedTurn(text, preset.answer!, preset.usage),
          mode: "replay",
          modeReason: "live assistant unavailable",
        }));
      } else {
        const message = error instanceof Error ? error.message : String(error);
        update(id, (turn) => ({ ...turn, status: "error", error: `Couldn't reach the assistant (${message}). Try a sample question.` }));
      }
    } finally {
      setBusy(false);
    }
  }

  function askSample(text: string) {
    const sample = samples.find((s) => s.question === text);
    if (sample?.answer) {
      add({ persona, turn: cachedTurn(sample.question, sample.answer, sample.usage) });
    } else {
      void askLive(text, persona);
    }
  }

  function runPreset(preset: Preset) {
    const who = demo.personas.find((p) => p.id === preset.persona) ?? persona;
    setPersonaId(who.id);
    void askLive(preset.question, who, preset);
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setQuestion("");
    void askLive(text, persona);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
      <aside className="flex flex-col gap-6">
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-muted">1. Pick who is asking</h2>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-1" role="radiogroup" aria-label="Persona">
            {demo.personas.map((p) => (
              <button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={p.id === persona.id}
                onClick={() => setPersonaId(p.id)}
                className={`rounded-lg border px-3 py-2 text-left text-sm transition ${p.id === persona.id ? "border-accent bg-accent-soft" : "border-border bg-surface hover:border-muted"}`}
              >
                <span className="block font-medium">{p.name}</span>
                <span className="block text-xs text-muted">
                  {p.title} · {p.region ?? "all regions"}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-muted">2. Ask a sample question</h2>
          <ul className="flex flex-col gap-1.5">
            {samples.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => askSample(s.question)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-left text-sm hover:border-accent"
                >
                  {s.question}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <BreakIt presets={demo.presets} personas={demo.personas} busy={busy} onRun={runPreset} />
      </aside>

      <section className="flex min-w-0 flex-col gap-4">
        {apiState !== "unknown" && apiState !== "ready" && (
          <p
            role="status"
            className={`rounded-lg border px-3 py-2 text-sm ${apiState === "unavailable" ? "border-danger/40 text-danger" : "border-border text-muted"}`}
          >
            {API_STATE_TEXT[apiState]}
          </p>
        )}
        {entries.length === 0 && (
          <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted">
            <p className="font-medium text-foreground">How to try it</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              <li>Pick a persona. Each one is a separate read-only database login.</li>
              <li>Click a sample question. Switch persona and ask a similar one: the answer changes.</li>
              <li>Open &quot;Show SQL&quot; and &quot;How this answer was built&quot; to check the evidence.</li>
              <li>Then try to break it: the attacks run live against the same agent.</li>
            </ol>
          </div>
        )}
        {entries.map((e) => (
          <AnswerCard
            key={e.id}
            turn={e.turn}
            personaName={`${e.persona.name} (${e.persona.title})`}
            evalLink={e.preset ? evalCaseUrl(e.preset.eval_file, e.preset.id) : undefined}
          />
        ))}
        {entries.some((e) => e.turn.mode === "replay" || e.turn.mode === "limited") && (
          <p className="text-xs text-muted">
            Replay and rate-limited answers come from precomputed results: the live demo has a daily
            budget and per-visitor limits.
          </p>
        )}
        <div ref={bottom} />
        <form onSubmit={submit} className="sticky bottom-0 flex gap-2 bg-background py-3">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <input
            id="question"
            value={question}
            maxLength={MAX_QUESTION}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={`Ask as ${persona.name}…`}
            className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            className="rounded-lg bg-accent px-4 py-2 font-medium text-background disabled:opacity-50"
          >
            Ask
          </button>
        </form>
      </section>
    </div>
  );
}

function BreakIt({
  presets,
  personas,
  busy,
  onRun,
}: {
  presets: Preset[];
  personas: Persona[];
  busy: boolean;
  onRun: (preset: Preset) => void;
}) {
  return (
    <section className="flex flex-col gap-2 rounded-xl border border-denied/40 p-3">
      <h2 className="text-sm font-medium">3. Try to break it</h2>
      <p className="text-xs text-muted">
        Prompt injection, role spoofing and SQL tricks. Each runs live and is also an eval case
        that must pass before any change merges.
      </p>
      <ul className="flex flex-col gap-1.5">
        {presets.map((p) => {
          const who = personas.find((x) => x.id === p.persona);
          return (
            <li key={p.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onRun(p)}
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-left text-sm hover:border-denied disabled:opacity-50"
              >
                <span className="block">{p.question}</span>
                <span className="block text-xs text-muted">as {who?.name ?? p.persona}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

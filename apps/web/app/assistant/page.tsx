import type { Metadata } from "next";

import { Assistant } from "@/components/assistant/Assistant";
import { DEMO } from "@/lib/demo";

export const metadata: Metadata = {
  title: "Governed AI Data Assistant",
  description:
    "Ask a fictional company's data a question as one of four roles. Every answer shows its evidence; access control is enforced by the database.",
};

export default function AssistantPage() {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Governed AI Data Assistant</h1>
        <p className="max-w-3xl text-muted">
          Harbourline Supply Co. is fictional; its data is synthetic. Each persona queries through
          its own read-only Postgres login, so row-level security and column grants decide what an
          answer can contain.
        </p>
      </header>
      <Assistant demo={DEMO} />
    </main>
  );
}

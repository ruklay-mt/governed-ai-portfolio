import Link from "next/link";

import { WarmUp } from "@/components/WarmUp";
import { SITE } from "@/lib/site";

const HIGHLIGHTS = [
  "Access control is enforced by Postgres (row-level security and column grants), not the prompt",
  "Every answer shows its evidence: the SQL, the rows, the cited policy passages",
  "A golden set of 31 evals gates every change in CI; leaking data fails the build",
  "Cost and latency on every answer, with a daily budget and rate limits",
];

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-10 px-4 py-16">
      <WarmUp />
      <section className="flex flex-col gap-3">
        <p className="text-sm text-muted">{SITE.role}</p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          AI that answers from company data, and can prove it was allowed to.
        </h1>
        <p className="text-lg text-muted">
          I build governed AI systems: agents with tools, measured by evals, with access control
          that holds even when the prompt is attacked.
        </p>
        <div className="flex flex-wrap gap-3 pt-2 text-sm">
          <a className="rounded-md border border-border px-3 py-1.5 hover:bg-surface" href={SITE.cvUrl}>
            CV
          </a>
          <a
            className="rounded-md border border-border px-3 py-1.5 hover:bg-surface"
            href={SITE.linkedinUrl}
          >
            LinkedIn
          </a>
          <a className="rounded-md border border-border px-3 py-1.5 hover:bg-surface" href={SITE.githubUrl}>
            GitHub
          </a>
        </div>
      </section>

      <section className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-6">
        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold">Governed AI Data Assistant</h2>
          <p className="text-muted">
            Ask a fictional NZ/AU distributor&apos;s ERP, CRM, service-desk and policy data a
            question. Switch roles and watch the answers change. Then try to break it.
          </p>
        </div>
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm">
          {HIGHLIGHTS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <div>
          <Link
            href="/assistant"
            className="inline-block rounded-md bg-accent px-4 py-2 font-medium text-background hover:opacity-90"
          >
            Try it (takes 3 minutes)
          </Link>
        </div>
      </section>
    </main>
  );
}

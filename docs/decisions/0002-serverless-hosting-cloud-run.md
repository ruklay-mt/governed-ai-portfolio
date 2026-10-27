# 0002 — Serverless hosting: Cloud Run + Vercel + Neon

- Status: Accepted (replaces D7 "Docker on existing VPS behind Caddy")
- Date: 2026-10-27

## Context

The VPS assumed in spec v0.1 is no longer available. The backend needs: streamed responses (SSE) of up to ~60 s, Python 3.12, outbound calls to the Claude API, and a budget of roughly US$0–30/month including LLM spend. Traffic is low and bursty (hiring managers clicking a link).

## Options considered

| Option | Cost | Notes |
|---|---|---|
| **Google Cloud Run** (`australia-southeast1`) | Mostly within free tier | Scale to zero, streaming supported, long request timeouts. Cold start of a few seconds. Needs a billing account. |
| Fly.io | ~US$3–5/month | Simple; no free tier for new accounts. |
| Render | Free tier sleeps (~1 min wake); US$7 for always-on | Free tier too slow for a demo. |
| New small VPS | ~€4–5/month | Keeps v0.1 design but adds server upkeep. |

## Decision

- **API:** FastAPI container on Cloud Run, Sydney region. `min-instances=0`, `max-instances=2` (a cost guard as well as a scale limit), request timeout 300 s.
- **Web:** Next.js on Vercel Hobby (unchanged, D8).
- **Database:** Neon Postgres + pgvector, Free plan, Sydney region (D1 accepted). `main` branch = prod, `dev` branch for development and evals.
- **Build and deploy:** GitHub Actions builds the image, pushes to Artifact Registry and deploys to Cloud Run using Workload Identity Federation — no service-account JSON keys anywhere.
- **Secrets:** GCP Secret Manager (API) and Vercel env (web). Never in the repo.
- **No Caddy, no docker-compose stack.** Cloud Run provides HTTPS. Docker is not required on the developer machine.

## Cold-start mitigation

1. Sample questions and their answers are precomputed at deploy and served statically from Vercel, so the first impression never waits on Cloud Run or Neon.
2. The landing page calls `/api/health` in the background to wake Cloud Run and Neon before the first live question.
3. The UI shows a "warming up" state rather than a spinner with no explanation.

## Consequences

- Process memory is not shared between instances, so rate-limit counters and the daily budget live in Postgres (spec §14).
- A GCP budget alert (~US$5) and an Anthropic Console spend limit are set before the public launch.
- Live-question latency includes up to two cold starts (Cloud Run + Neon) after idle periods. Accepted; measured and shown on the trace.

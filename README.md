# Governed AI Data Assistant

A portfolio project: an AI agent over a fictional company's ERP, CRM, service-desk and policy data.
Answers change by role, every answer shows its evidence (SQL, citations), and access control is
enforced in the database, not the prompt.

Status: under construction (MVP in progress). All data is synthetic.

- Spec: [docs/spec.md](docs/spec.md)
- Phase plan: [docs/phases.md](docs/phases.md)
- Design decisions: [docs/decisions/](docs/decisions/)

## Run locally

Requires [uv](https://docs.astral.sh/uv/), Node 20+ and [pnpm](https://pnpm.io/).

```bash
cp .env.example .env   # then fill in DATABASE_URL
make setup
make db-migrate
make test
make api-dev           # http://localhost:8000/api/health
make web-dev           # http://localhost:3000
```

Built with [Claude Code](https://claude.com/claude-code) as a pair; design decisions are recorded as ADRs.

## Licence

MIT

# 0006 — Accept remaining defaults; lower the daily LLM budget

- Status: Accepted
- Date: 2026-10-27

## Decision

| Item | Decision |
|---|---|
| D4 Semantic layer | Own lightweight YAML → SQL compiler (default accepted). Small enough to explain line by line. |
| D9 Names | Company "Harbourline Supply Co."; product "Governed AI Data Assistant". |
| D10 Repo | Public, MIT licence. |
| Daily LLM budget | **US$1.00/day** (was US$1.50). At full use that is ~US$30/month, matching the §1 cost goal. Env `DAILY_BUDGET_USD`. |

## Still open

- MCP persona selection (fixed `sales_manager` vs header) — decide when the MCP server is built.
- Portfolio domain / subdomain.
- Visual design and copy (§9).

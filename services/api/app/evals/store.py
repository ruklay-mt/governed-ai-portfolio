"""Save eval runs to evals.eval_runs / evals.eval_results as app_service (migration 0005)."""

import json

import psycopg

from app.agent.db import CONNECT_TIMEOUT_SECONDS, persona_url
from app.config import Settings
from app.evals.report import CaseResult, RunSummary


def store_run(settings: Settings, summary: RunSummary, results: list[CaseResult]) -> bool:
    """False when app_service is not configured; raises on a database error."""
    password = settings.app_service_db_password
    if settings.database_url is None or password is None:
        return False
    url = persona_url(settings.database_url, "app_service", password.get_secret_value())
    by_category = {
        k: v.model_dump() | {"pass_rate": v.pass_rate} for k, v in summary.by_category.items()
    }
    with (
        psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS) as conn,
        conn.transaction(),
    ):
        conn.execute(
            "insert into evals.eval_runs (run_id, started_at, finished_at, git_sha, run_trigger,"
            " model_main, model_small, total_cases, passed_cases, pass_rate, by_category,"
            " cost_usd, gate_passed, gate_reasons)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                summary.run_id, summary.started_at, summary.finished_at, summary.git_sha,
                summary.trigger, summary.model_main, summary.model_small, summary.total,
                summary.passed, round(summary.pass_rate, 4), json.dumps(by_category),
                summary.cost_usd, summary.gate_passed, json.dumps(summary.gate_reasons),
            ),
        )  # fmt: skip
        with conn.cursor() as cur:
            cur.executemany(
                "insert into evals.eval_results (run_id, case_id, attempt, category, persona,"
                " question, passed, checks, answer, latency_ms, cost_usd, trace_id)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        summary.run_id, r.case_id, r.attempt, r.category, r.persona, r.question,
                        r.passed, json.dumps([c.model_dump() for c in r.checks]),
                        json.dumps(r.answer, default=str), r.latency_ms, r.cost_usd, r.trace_id,
                    )
                    for r in results
                ],
            )  # fmt: skip
    return True

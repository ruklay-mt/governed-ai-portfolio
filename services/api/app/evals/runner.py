"""Run the golden set against the live agent and apply the merge gate (spec §12, ADR 0012).

    make eval                                  # all cases; exit 1 if the gate fails
    make eval ARGS="--only ac-rep-margin"      # specific cases (comma-separated)
    make eval ARGS="--category access_control --repeat 3"   # measure flakiness

Each case runs once: no retries, because a retry hides a flaky answer instead of measuring it.
The run stops (and fails) once its cost passes `max_cost_usd` in evals/config.yml. Eval spend
is recorded in evals.eval_runs, not in ops.daily_spend, which is the public site's budget.
"""

import argparse
import os
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime

import psycopg

from app.agent.record import RunRecord, collect_run
from app.config import get_settings
from app.evals.cases import EVALS_DIR, EvalCase, load_cases, load_config
from app.evals.checks import JudgeVerdict, Reference, run_checks
from app.evals.judge import judge
from app.evals.report import CaseResult, RunSummary, gate, score, to_markdown, write_report
from app.evals.store import store_run
from app.runtime import Runtime, build_runtime

REFERENCE_MAX_ROWS = 100


def _git_sha() -> str | None:
    if sha := os.environ.get("GITHUB_SHA"):
        return sha
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        return out.stdout.strip() or None
    except OSError:
        return None


def reference_rows(runtime: Runtime, case: EvalCase, today: date) -> Reference | None:
    """Run the case's reference SQL as a persona login (the case's own unless `as_persona`),
    so RLS and grants apply to the reference exactly as they do to the agent."""
    spec = case.expect.result_match
    if spec is None:
        return None
    try:
        with runtime.deps.pools.transaction(spec.as_persona or case.persona) as conn:
            cursor = conn.execute(spec.sql, {"today": today})
            columns = [d.name for d in cursor.description or []]
            rows = [list(r) for r in cursor.fetchmany(REFERENCE_MAX_ROWS)]
    except psycopg.Error as error:
        print(f"     ! reference query failed: {error}", file=sys.stderr)
        return None
    return Reference(columns=columns, rows=rows)


def run_case(
    runtime: Runtime, case: EvalCase, run_id: str, attempt: int, today: date
) -> CaseResult:
    run: RunRecord = collect_run(
        runtime.deps,
        case.persona,
        case.question,
        today,
        trace_metadata={"eval_run": run_id, "eval_case": case.id},
    )
    cost = run.cost_usd
    verdict: JudgeVerdict | None = None
    if case.expect.judge and run.answer:
        settings = runtime.deps.settings
        verdict, judge_cost = judge(
            runtime.deps.client,
            settings.model_small or "",
            case.question,
            run.answer,
            case.expect.judge,
        )
        cost += judge_cost
    checks = run_checks(case, run, reference_rows(runtime, case, today), verdict)
    return CaseResult(
        case_id=case.id,
        attempt=attempt,
        category=case.category,
        persona=case.persona,
        question=case.question,
        preset=case.preset,
        passed=all(c.passed for c in checks),
        checks=checks,
        answer=run.answer,
        tools=run.tools,
        tool_results=run.tool_results,
        latency_ms=run.usage.get("latency_ms"),
        cost_usd=round(cost, 6),
        trace_id=run.trace_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--category", help="only this category")
    parser.add_argument("--repeat", type=int, default=1, help="run each case N times")
    parser.add_argument("--no-store", action="store_true", help="do not write to evals.*")
    args = parser.parse_args()

    only = set(args.only.split(",")) if args.only else None
    cases = [
        c
        for c in load_cases()
        if (not only or c.id in only) and (not args.category or c.category == args.category)
    ]
    if only and (unknown := only - {c.id for c in cases}):
        print(f"unknown case ids: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    config = load_config()
    settings = get_settings()
    runtime = build_runtime(settings)
    run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    today = date.today()
    results: list[CaseResult] = []
    total_cost = 0.0
    aborted: str | None = None

    try:
        for case in cases:
            for attempt in range(1, args.repeat + 1):
                if total_cost >= config.max_cost_usd:
                    aborted = f"cost ${total_cost:.2f} reached max_cost_usd {config.max_cost_usd}"
                    break
                result = run_case(runtime, case, run_id, attempt, today)
                results.append(result)
                total_cost += result.cost_usd
                status = "PASS" if result.passed else "FAIL"
                print(
                    f"{status} {case.id:<34} {result.latency_ms or 0:>6} ms  "
                    f"${result.cost_usd:.4f}  tools={','.join(result.tools) or '-'}"
                )
                for check in result.checks:
                    if not check.passed:
                        print(f"     ! {check.name}: {check.detail}")
                for tool in result.tool_results:
                    if tool.get("status") == "error":
                        print(f"     ~ {tool.get('tool')} error: {tool.get('message')}")
            if aborted:
                break
    finally:
        runtime.deps.pools.close()
        runtime.guard.close()

    passed, reasons = gate(results, config, aborted)
    summary = RunSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(timespec="seconds"),
        git_sha=_git_sha(),
        trigger="ci" if os.environ.get("CI") else "local",
        model_main=settings.model_main or "",
        model_small=settings.model_small or "",
        total=len(results),
        passed=sum(r.passed for r in results),
        pass_rate=round(sum(r.passed for r in results) / len(results), 4) if results else 0.0,
        by_category=score(results),
        cost_usd=round(total_cost, 6),
        gate_passed=passed,
        gate_reasons=reasons,
        aborted=aborted,
    )
    report = write_report(summary, results, EVALS_DIR / "reports")
    if not args.no_store:
        try:
            if not store_run(settings, summary, results):
                print("app_service not configured: run not stored in evals.*", file=sys.stderr)
        except psycopg.Error as error:
            print(f"could not store run: {error}", file=sys.stderr)

    print("\n" + to_markdown(summary, []))
    print(f"report: {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

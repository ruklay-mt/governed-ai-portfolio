"""Run the sample questions and "Try to break it" presets live (spends real tokens).

    make agent-smoke     # check every sample and preset, print pass/fail, tokens and cost
    make samples-build   # same, write passing answers to answers/<id>.json, then the web's
                         # static demo data (export.py)

Samples are checked against their `expect` in samples.yml; presets against their eval case's
checks, so a preset answer is only cached when it would also pass the eval gate.

Options: --persona <id> to run one persona, --only <id,id> to run specific samples.
Spend is recorded in ops.daily_spend (when app_service is configured), so these runs count
against the same daily budget as the live site.
"""

import argparse
import json
import sys
from datetime import UTC, date, datetime
from typing import Any

from app.agent.record import RunRecord, collect_run
from app.config import get_settings
from app.evals.checks import run_checks
from app.evals.runner import reference_rows
from app.runtime import Runtime, build_runtime
from app.samples.catalogue import (
    ANSWERS_DIR,
    CachedAnswer,
    Preset,
    Sample,
    check_expectations,
    load_presets,
    load_samples,
)
from app.samples.export import write_demo


def problems_with(
    runtime: Runtime, item: Sample | Preset, run: RunRecord, today: date
) -> list[str]:
    if isinstance(item, Sample):
        return run.errors + check_expectations(item, run.answer)
    checks = run_checks(item.case, run, reference_rows(runtime, item.case, today))
    return [f"{c.name}: {c.detail}" for c in checks if not c.passed]


def write_answer(item_id: str, answer: dict[str, Any], usage: dict[str, Any]) -> None:
    ANSWERS_DIR.mkdir(exist_ok=True)
    cached = CachedAnswer(
        sample_id=item_id,
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        answer=answer,
        usage=usage,
    )
    (ANSWERS_DIR / f"{item_id}.json").write_text(
        json.dumps(cached.model_dump(), indent=2, default=str) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write passing answers to disk")
    parser.add_argument("--persona", help="only this persona")
    parser.add_argument("--only", help="comma-separated sample or preset ids")
    args = parser.parse_args()

    only = set(args.only.split(",")) if args.only else None
    everything: list[Sample | Preset] = [*load_samples(), *load_presets()]
    items = [
        item
        for item in everything
        if (not args.persona or item.persona == args.persona) and (not only or item.id in only)
    ]
    runtime = build_runtime(get_settings())
    today = date.today()
    total_cost = 0.0
    failures = 0

    for item in items:
        run = collect_run(runtime.deps, item.persona, item.question, today)
        cost = run.cost_usd
        total_cost += cost
        runtime.guard.record_spend(cost)

        problems = problems_with(runtime, item, run, today)
        status = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        print(
            f"{status} {item.id:<28} {run.usage.get('latency_ms', 0):>6} ms  ${cost:.4f}"
            f"  tools={','.join(run.tools) or '-'}"
        )
        print(f"     {str(run.answer.get('text', ''))[:220]}")
        for problem in problems:
            print(f"     ! {problem}")

        if args.write and not problems:
            write_answer(item.id, run.answer, run.usage)

    if args.write:
        print(f"wrote {write_demo()}")
    print(f"\n{len(items) - failures}/{len(items)} passed, total cost ${total_cost:.4f}")
    runtime.deps.pools.close()
    runtime.guard.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

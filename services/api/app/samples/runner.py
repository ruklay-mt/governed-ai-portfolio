"""Run the sample questions live against the agent (spends real tokens).

    make agent-smoke     # check every sample, print pass/fail, tokens and cost
    make samples-build   # same, and write passing answers to answers/<id>.json

Options: --persona <id> to run one persona, --only <id,id> to run specific samples.
Spend is recorded in ops.daily_spend (when app_service is configured), so these runs count
against the same daily budget as the live site.
"""

import argparse
import json
import sys
from datetime import UTC, datetime

from app.agent.loop import run_agent
from app.config import get_settings
from app.runtime import build_runtime
from app.samples.catalogue import ANSWERS_DIR, CachedAnswer, check_expectations, load_samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write passing answers to disk")
    parser.add_argument("--persona", help="only this persona")
    parser.add_argument("--only", help="comma-separated sample ids")
    args = parser.parse_args()

    only = set(args.only.split(",")) if args.only else None
    samples = [
        s
        for s in load_samples()
        if (not args.persona or s.persona == args.persona) and (not only or s.id in only)
    ]
    runtime = build_runtime(get_settings())
    total_cost = 0.0
    failures = 0

    for sample in samples:
        answer: dict[str, object] = {}
        usage: dict[str, object] = {}
        errors: list[str] = []
        tools: list[str] = []
        for event in run_agent(runtime.deps, sample.persona, sample.question):
            if event.type == "answer":
                answer = event.data
            elif event.type == "usage":
                usage = event.data
            elif event.type == "tool_result":
                tools.append(f"{event.data['tool']}:{event.data['status']}")
            elif event.type == "error":
                errors.append(str(event.data["message"]))
        cost = float(str(usage.get("cost_usd", 0.0)))
        total_cost += cost
        runtime.guard.record_spend(cost)

        problems = errors + check_expectations(sample, answer)
        status = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        print(
            f"{status} {sample.id:<26} {usage.get('latency_ms', 0):>6} ms  ${cost:.4f}"
            f"  tools={','.join(tools) or '-'}"
        )
        print(f"     {str(answer.get('text', ''))[:220]}")
        for problem in problems:
            print(f"     ! {problem}")

        if args.write and not problems:
            ANSWERS_DIR.mkdir(exist_ok=True)
            cached = CachedAnswer(
                sample_id=sample.id,
                built_at=datetime.now(UTC).isoformat(timespec="seconds"),
                answer=answer,
                usage=usage,
            )
            (ANSWERS_DIR / f"{sample.id}.json").write_text(
                json.dumps(cached.model_dump(), indent=2, default=str) + "\n", encoding="utf-8"
            )

    print(f"\n{len(samples) - failures}/{len(samples)} passed, total cost ${total_cost:.4f}")
    runtime.deps.pools.close()
    runtime.guard.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

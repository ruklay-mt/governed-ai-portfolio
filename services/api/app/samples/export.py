"""Write the web app's static demo data (ADR 0013).

    make samples-export   # no tokens: reads samples.yml, eval presets and answers/*.json

The web bundle imports apps/web/data/demo.json at build time, so personas, sample answers and
preset replays render with no API call: the first answer is instant even while Cloud Run and
Neon are still waking up. `make samples-build --write` runs this at the end.
"""

import json
from pathlib import Path
from typing import Any

from app.agent.personas import PERSONAS
from app.evals.cases import REPO_ROOT
from app.samples.catalogue import ANSWERS_DIR, cached_answer, load_presets, load_samples

DEMO_FILE = REPO_ROOT / "apps" / "web" / "data" / "demo.json"


def demo_data(answers_dir: Path = ANSWERS_DIR) -> dict[str, Any]:
    def cached(item_id: str) -> dict[str, Any]:
        answer = cached_answer(item_id, answers_dir)
        if answer is None:
            return {"answer": None, "usage": None}
        return {"answer": answer.answer, "usage": answer.usage}

    return {
        "personas": [
            {
                "id": p.id,
                "name": p.name,
                "title": p.title,
                "location": p.location,
                "region": p.region,
                "role": p.role,
            }
            for p in PERSONAS.values()
        ],
        "samples": [
            {"id": s.id, "persona": s.persona, "question": s.question, **cached(s.id)}
            for s in load_samples()
        ],
        "presets": [
            {
                "id": p.id,
                "persona": p.persona,
                "question": p.question,
                "category": p.category,
                "eval_file": p.eval_file,
                **cached(p.id),
            }
            for p in load_presets()
        ],
    }


def write_demo(path: Path = DEMO_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(demo_data(), indent=2, default=str) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(f"wrote {write_demo()}")

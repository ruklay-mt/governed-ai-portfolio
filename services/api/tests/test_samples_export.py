import json
from pathlib import Path

from app.evals.cases import load_cases
from app.samples.catalogue import find_preset, load_presets
from app.samples.export import demo_data, write_demo


def test_presets_match_the_eval_cases_marked_preset() -> None:
    expected = {c.id for c in load_cases() if c.preset}
    assert {p.id for p in load_presets()} == expected


def test_find_preset_ignores_case_and_trailing_punctuation() -> None:
    preset = load_presets()[0]
    assert find_preset(preset.persona, preset.question.upper().rstrip(".") + "?") == preset
    assert (
        find_preset("finance" if preset.persona != "finance" else "support", preset.question)
        is None
    )


def test_demo_data_includes_cached_answers(tmp_path: Path) -> None:
    preset = load_presets()[0]
    (tmp_path / f"{preset.id}.json").write_text(
        json.dumps(
            {
                "sample_id": preset.id,
                "built_at": "2026-10-28",
                "answer": {"text": "No."},
                "usage": {},
            }
        )
    )
    data = demo_data(tmp_path)
    assert len(data["personas"]) == 4
    by_id = {p["id"]: p for p in data["presets"]}
    assert by_id[preset.id]["answer"] == {"text": "No."}
    assert all(s["answer"] is None for s in data["samples"])


def test_committed_demo_file_is_up_to_date(tmp_path: Path) -> None:
    # The web app imports apps/web/data/demo.json; run `make samples-export` if this fails.
    from app.samples.export import DEMO_FILE

    fresh = write_demo(tmp_path / "demo.json")
    assert json.loads(DEMO_FILE.read_text()) == json.loads(fresh.read_text())

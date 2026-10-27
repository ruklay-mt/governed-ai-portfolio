import pytest

from app.config import Settings


def test_model_names_have_no_hard_coded_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_MAIN", raising=False)
    monkeypatch.delenv("MODEL_SMALL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.model_main is None
    assert settings.model_small is None


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_MAIN", "model-from-env")
    monkeypatch.setenv("DAILY_BUDGET_USD", "0.5")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.test, https://b.example.test")

    settings = Settings(_env_file=None)

    assert settings.model_main == "model-from-env"
    assert settings.daily_budget_usd == 0.5
    assert settings.cors_origins == ["https://a.example.test", "https://b.example.test"]

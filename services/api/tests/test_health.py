import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_settings(**values: object) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **values)


def test_health_without_database(client: TestClient) -> None:
    use_settings(database_url=None)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "not_configured"}


def test_health_reports_unreachable_database(client: TestClient) -> None:
    # Port 1 on localhost refuses connections immediately.
    use_settings(database_url="postgresql://nobody@127.0.0.1:1/none")

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "unavailable"}


@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs DATABASE_URL")
def test_health_with_database(client: TestClient) -> None:
    use_settings(database_url=os.environ["DATABASE_URL"])

    response = client.get("/api/health")

    assert response.json() == {"status": "ok", "db": "ok"}

"""FastAPI application."""

from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db
from app.agent.db import persona_url
from app.config import Settings, get_settings
from app.routes import router

app = FastAPI(title="Governed AI Data Assistant API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router)


class Health(BaseModel):
    status: Literal["ok"]
    db: Literal["ok", "unavailable", "not_configured"]


@app.get("/api/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> Health:
    """Liveness check that also wakes the database.

    Always returns 200 while the process is up; the `db` field reports database reachability.
    It connects as `app_service` when that login is configured: in production DATABASE_URL
    carries only the host and database name, so the API never holds the owner's password.
    """
    if settings.database_url is None:
        return Health(status="ok", db="not_configured")
    url = settings.database_url
    if settings.app_service_db_password is not None:
        password = settings.app_service_db_password.get_secret_value()
        url = persona_url(url, "app_service", password)
    return Health(status="ok", db="ok" if db.ping(url) else "unavailable")

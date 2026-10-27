"""FastAPI application."""

from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import db
from app.config import Settings, get_settings

app = FastAPI(title="Governed AI Data Assistant API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class Health(BaseModel):
    status: Literal["ok"]
    db: Literal["ok", "unavailable", "not_configured"]


@app.get("/api/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> Health:
    """Liveness check that also wakes the database.

    Always returns 200 while the process is up; the `db` field reports database reachability.
    """
    if settings.database_url is None:
        return Health(status="ok", db="not_configured")
    return Health(status="ok", db="ok" if db.ping(settings.database_url) else "unavailable")

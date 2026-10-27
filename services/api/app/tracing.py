"""Langfuse tracing (spec §13, ADR 0004): one trace per chat request.

Spans are created explicitly (parent.child(...)) instead of through "current span" context,
because the agent loop is a generator that the SSE response consumes across threads, and
context-local state does not survive that. Tracing must never fail a request: every call is
wrapped, and without Langfuse keys all spans are no-ops.
"""

import logging
from typing import Any, Literal

from langfuse import Langfuse

from app.config import Settings

logger = logging.getLogger(__name__)

ObservationType = Literal["span", "agent", "tool", "generation", "guardrail", "retriever"]


class Span:
    """A Langfuse observation, or a no-op when tracing is off or broken."""

    def __init__(self, observation: Any | None) -> None:
        self._observation = observation

    @property
    def trace_id(self) -> str | None:
        return getattr(self._observation, "trace_id", None)

    def child(self, name: str, as_type: ObservationType = "span", **fields: Any) -> "Span":
        if self._observation is None:
            return Span(None)
        try:
            return Span(self._observation.start_observation(name=name, as_type=as_type, **fields))
        except Exception:
            logger.exception("tracing: could not start %s", name)
            return Span(None)

    def end(self, **fields: Any) -> None:
        if self._observation is None:
            return
        try:
            if fields:
                self._observation.update(**fields)
            self._observation.end()
        except Exception:
            logger.exception("tracing: could not end span")


class Tracer:
    def __init__(self, settings: Settings) -> None:
        self._client: Langfuse | None = None
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                self._client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key.get_secret_value(),
                    host=settings.langfuse_host,
                )
            except Exception:
                logger.exception("tracing: Langfuse client unavailable")

    def trace(self, name: str, **fields: Any) -> Span:
        if self._client is None:
            return Span(None)
        try:
            return Span(self._client.start_observation(name=name, as_type="agent", **fields))
        except Exception:
            logger.exception("tracing: could not start trace")
            return Span(None)

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception:
            logger.exception("tracing: flush failed")

"""Read APIs and the chat endpoint (spec §9)."""

import json
from collections.abc import Iterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.cost import UnknownModelPrice
from app.agent.loop import Event, run_agent
from app.agent.personas import PERSONAS
from app.runtime import Runtime, RuntimeUnavailable, get_runtime
from app.samples.catalogue import cached_answer, find_sample, load_samples

router = APIRouter(prefix="/api")

REPLAY_MESSAGE = (
    "Live answers are paused ({reason}). Sample questions still work from cached answers - "
    "pick one from the list."
)


class PersonaOut(BaseModel):
    id: str
    name: str
    title: str
    location: str
    region: str | None
    role: str


class SampleOut(BaseModel):
    id: str
    persona: str
    question: str
    answer: dict[str, Any] | None
    usage: dict[str, Any] | None


class ChatRequest(BaseModel):
    persona: str
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=500)


@router.get("/personas")
def personas() -> list[PersonaOut]:
    return [
        PersonaOut(
            id=p.id, name=p.name, title=p.title, location=p.location, region=p.region, role=p.role
        )
        for p in PERSONAS.values()
    ]


@router.get("/samples")
def samples(persona: str | None = None) -> list[SampleOut]:
    out: list[SampleOut] = []
    for sample in load_samples():
        if persona and sample.persona != persona:
            continue
        cached = cached_answer(sample.id)
        out.append(
            SampleOut(
                id=sample.id,
                persona=sample.persona,
                question=sample.question,
                answer=cached.answer if cached else None,
                usage=cached.usage if cached else None,
            )
        )
    return out


def _sse(event: Event) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.data, default=str)}\n\n"


def _mode(mode: Literal["live", "cached", "replay", "limited"], reason: str | None) -> str:
    return f"event: mode\ndata: {json.dumps({'mode': mode, 'reason': reason})}\n\n"


def client_ip(request: Request) -> str:
    # Cloud Run sets X-Forwarded-For; the first hop is the visitor.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _runtime() -> Runtime:
    try:
        return get_runtime()
    except (RuntimeUnavailable, UnknownModelPrice, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=f"assistant unavailable: {error}") from None


@router.post("/chat")
def chat(
    body: ChatRequest, request: Request, runtime: Annotated[Runtime, Depends(_runtime)]
) -> StreamingResponse:
    """Stream the answer as server-sent events.

    Events: mode, trace_id, step, tool_call, tool_result, answer, usage, error.
    """
    if body.persona not in PERSONAS:
        raise HTTPException(status_code=422, detail=f"unknown persona {body.persona!r}")

    def stream() -> Iterator[str]:
        sample = find_sample(body.persona, body.message)
        cached = cached_answer(sample.id) if sample else None
        if cached is not None:
            yield _mode("cached", "sample question")
            yield _sse(Event(type="answer", data=cached.answer))
            yield _sse(Event(type="usage", data={**cached.usage, "cost_usd": 0.0}))
            return

        admission = runtime.guard.admit(body.session_id, client_ip(request))
        if admission.mode != "live":
            yield _mode(admission.mode, admission.reason)
            text = REPLAY_MESSAGE.format(reason=admission.reason)
            yield _sse(Event(type="answer", data={"text": text}))
            return

        yield _mode("live", None)
        cost = 0.0
        for event in run_agent(runtime.deps, body.persona, body.message):
            if event.type == "usage":
                cost = float(event.data.get("cost_usd", 0.0))
            yield _sse(event)
        runtime.guard.record_spend(cost)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

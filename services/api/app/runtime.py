"""Long-lived objects the chat endpoint needs: model client, DB pools, cost guard, tracer.

Built once per process on first use (Cloud Run keeps an instance warm between requests).
Tests replace `get_runtime` with a fake through FastAPI's dependency overrides.
"""

from dataclasses import dataclass
from functools import lru_cache

import anthropic

from app.agent.cost import price_for
from app.agent.db import PersonaPools
from app.agent.loop import AgentDeps
from app.config import Settings, get_settings
from app.ops.guards import CostGuard
from app.retrieval.embeddings import Embedder
from app.tracing import Tracer


@dataclass
class Runtime:
    deps: AgentDeps
    guard: CostGuard


class RuntimeUnavailable(RuntimeError):
    pass


def build_runtime(settings: Settings) -> Runtime:
    if settings.anthropic_api_key is None or not settings.model_main or not settings.model_small:
        raise RuntimeUnavailable("ANTHROPIC_API_KEY, MODEL_MAIN and MODEL_SMALL must be set")
    # Fail closed on a model we cannot price: the daily budget could not be enforced.
    price_for(settings.model_main)
    price_for(settings.model_small)
    embedder = Embedder(settings)
    deps = AgentDeps(
        client=anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(), timeout=60.0, max_retries=2
        ),
        settings=settings,
        pools=PersonaPools(settings),
        embed_query=lambda text: embedder.embed([text], "query")[0],
        tracer=Tracer(settings),
    )
    return Runtime(deps=deps, guard=CostGuard(settings))


@lru_cache
def get_runtime() -> Runtime:
    return build_runtime(get_settings())

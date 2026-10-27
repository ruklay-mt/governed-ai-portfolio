"""Cost of a model call in USD, from its token usage (spec §16: cost is a feature).

Prices are Anthropic first-party rates per million tokens (checked 2026-10-27 against the
pricing table). Model names still come from the environment (CLAUDE.md rule 5); this table only
prices them. A model missing here fails closed: the API will not answer live with a model it
cannot price, because it could not enforce the daily budget.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float  # 5-minute cache writes cost 1.25x input


PRICES_PER_MTOK: dict[str, Price] = {
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.20, cache_write=2.50),
    # Haiku 5.5 rates apply to prompts up to 100K tokens; the guard prompt is far smaller.
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
}


class UnknownModelPrice(RuntimeError):
    pass


class Usage(Protocol):
    """The fields of anthropic's Usage object that cost depends on."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None


def price_for(model: str) -> Price:
    try:
        return PRICES_PER_MTOK[model]
    except KeyError:
        raise UnknownModelPrice(f"no price for model {model!r}; add it to agent/cost.py") from None


def call_cost_usd(model: str, usage: Usage) -> float:
    price = price_for(model)
    cost = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + (usage.cache_read_input_tokens or 0) * price.cache_read
        + (usage.cache_creation_input_tokens or 0) * price.cache_write
    ) / 1_000_000
    return round(cost, 6)


def usage_details(usage: Usage) -> dict[str, int]:
    """Token counts in the shape Langfuse and the API response use."""
    return {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cache_read": usage.cache_read_input_tokens or 0,
        "cache_write": usage.cache_creation_input_tokens or 0,
    }

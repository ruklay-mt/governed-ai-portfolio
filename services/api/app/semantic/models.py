"""Pydantic models for the semantic layer: the YAML definitions and the compiler's input/output."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Grain = Literal["day", "week", "month", "quarter", "year"]

MAX_LIMIT = 1000


class Model(BaseModel):
    """A fact table a metric is computed from."""

    model_config = ConfigDict(extra="forbid")

    table: str
    alias: str
    date_column: str
    description: str


class Dimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    join: str | None = None
    expressions: dict[str, str]  # model name -> SQL expression


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    model: str
    expression: str
    unit: Literal["NZD", "percent", "count"]
    roles: list[str]


class SemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: dict[str, Model]
    joins: dict[str, str]
    dimensions: dict[str, Dimension]
    metrics: dict[str, Metric]


class MetricRequest(BaseModel):
    """What the agent's `get_metric` tool asks for. Every name must exist in metrics.yml."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    dimensions: list[str] = Field(default_factory=list, max_length=3)
    # dimension name -> one value or a list of values (matched exactly)
    filters: dict[str, str | list[str]] = Field(default_factory=dict)
    # A preset such as "last_quarter", or "YYYY-MM-DD..YYYY-MM-DD" (both ends inclusive).
    # None means all available history.
    time_range: str | None = None
    grain: Grain | None = None
    limit: int = Field(default=100, ge=1, le=MAX_LIMIT)


class ResolvedRange(BaseModel):
    start: date
    end: date  # inclusive
    label: str


class CompiledQuery(BaseModel):
    """SQL with bound parameters, plus what the compiler assumed while building it."""

    metric: str
    sql: str
    params: dict[str, Any]
    columns: list[str]
    time_range: ResolvedRange | None
    assumptions: list[str]

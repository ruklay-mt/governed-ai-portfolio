"""Compile a MetricRequest into SQL against the marts (spec §7).

Only names from metrics.yml reach the SQL text; filter values and dates are bound parameters.
The compiled query still runs as the caller's persona login, so a mistake here cannot widen
access: the database decides which rows and columns come back.
"""

import calendar
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from app.semantic.models import (
    CompiledQuery,
    MetricRequest,
    ResolvedRange,
    SemanticModel,
)

METRICS_FILE = Path(__file__).parent / "metrics.yml"
TIME_PRESETS = (
    "last_7_days",
    "last_30_days",
    "this_month",
    "last_month",
    "this_quarter",
    "last_quarter",
    "ytd",
    "last_year",
    "last_12_months",
)
_EXPLICIT_RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")


class SemanticError(ValueError):
    """The request names something that does not exist or cannot be combined."""


class MetricNotAllowed(SemanticError):
    """The caller's role may not use this metric (spec §7: e.g. gross_margin is finance only)."""


@lru_cache
def load_semantic_model(path: Path = METRICS_FILE) -> SemanticModel:
    model = SemanticModel.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    for name, metric in model.metrics.items():
        if metric.model not in model.models:
            raise ValueError(f"metric {name}: unknown model {metric.model}")
    for name, dimension in model.dimensions.items():
        if dimension.join is not None and dimension.join not in model.joins:
            raise ValueError(f"dimension {name}: unknown join {dimension.join}")
        if unknown := set(dimension.expressions) - set(model.models):
            raise ValueError(f"dimension {name}: unknown models {sorted(unknown)}")
    return model


def allowed_metrics(role: str, model: SemanticModel | None = None) -> list[str]:
    model = model or load_semantic_model()
    return [name for name, metric in model.metrics.items() if role in metric.roles]


def _quarter_start(day: date) -> date:
    return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def resolve_time_range(value: str, today: date) -> ResolvedRange:
    """Turn a preset or explicit range into inclusive dates. Calendar periods, not fiscal."""
    if match := _EXPLICIT_RANGE.match(value):
        start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2])
        if start > end:
            raise SemanticError(f"time range starts after it ends: {value}")
        return ResolvedRange(start=start, end=end, label=value)

    if value == "last_7_days":
        start, end = today - timedelta(days=6), today
    elif value == "last_30_days":
        start, end = today - timedelta(days=29), today
    elif value == "this_month":
        start, end = today.replace(day=1), today
    elif value == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif value == "this_quarter":
        start, end = _quarter_start(today), today
    elif value == "last_quarter":
        end = _quarter_start(today) - timedelta(days=1)
        start = _quarter_start(end)
        end = _month_end(end.year, end.month)
    elif value == "ytd":
        start, end = date(today.year, 1, 1), today
    elif value == "last_year":
        start, end = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    elif value == "last_12_months":
        start, end = today - timedelta(days=364), today
    else:
        raise SemanticError(
            f"unknown time_range {value!r}; use one of {', '.join(TIME_PRESETS)}"
            " or YYYY-MM-DD..YYYY-MM-DD"
        )
    return ResolvedRange(start=start, end=end, label=value)


def compile_metric(
    request: MetricRequest,
    role: str,
    today: date | None = None,
    model: SemanticModel | None = None,
) -> CompiledQuery:
    model = model or load_semantic_model()
    today = today or date.today()

    metric = model.metrics.get(request.metric)
    if metric is None:
        raise SemanticError(
            f"unknown metric {request.metric!r}; available: {', '.join(model.metrics)}"
        )
    if role not in metric.roles:
        raise MetricNotAllowed(f"metric {request.metric!r} is not available to role {role}")
    fact = model.models[metric.model]

    def dimension_expression(name: str) -> tuple[str, str | None]:
        dimension = model.dimensions.get(name)
        if dimension is None:
            raise SemanticError(
                f"unknown dimension {name!r}; available: {', '.join(model.dimensions)}"
            )
        expression = dimension.expressions.get(metric.model)
        if expression is None:
            raise SemanticError(f"dimension {name!r} does not apply to metric {request.metric!r}")
        return expression, dimension.join

    if len(set(request.dimensions)) != len(request.dimensions):
        raise SemanticError("dimensions must not repeat")

    select: list[str] = []
    columns: list[str] = []
    joins: list[str] = []
    where: list[str] = []
    params: dict[str, object] = {}
    assumptions: list[str] = [f"{request.metric}: {metric.description}"]

    def add_join(join: str | None) -> None:
        if join is not None:
            clause = model.joins[join].format(alias=fact.alias)
            if clause not in joins:
                joins.append(clause)

    if request.grain is not None:
        select.append(f"date_trunc('{request.grain}', {fact.date_column})::date as period")
        columns.append("period")
    for name in request.dimensions:
        expression, join = dimension_expression(name)
        add_join(join)
        select.append(f"{expression} as {name}")
        columns.append(name)
    select.append(f"{metric.expression} as {request.metric}")
    columns.append(request.metric)

    resolved: ResolvedRange | None = None
    if request.time_range is not None:
        resolved = resolve_time_range(request.time_range, today)
        where.append(f"{fact.date_column} between %(start_date)s and %(end_date)s")
        params["start_date"], params["end_date"] = resolved.start, resolved.end
        assumptions.append(
            f"{resolved.label} = {resolved.start.isoformat()} to {resolved.end.isoformat()}"
            " (calendar dates)"
        )
    else:
        assumptions.append("all available history (no time range given)")

    for index, (name, value) in enumerate(sorted(request.filters.items())):
        expression, join = dimension_expression(name)
        add_join(join)
        values = [value] if isinstance(value, str) else value
        if not values:
            raise SemanticError(f"filter {name!r} has no values")
        param = f"filter_{index}"
        where.append(f"{expression} = any(%({param})s)")
        params[param] = values

    group_count = len(columns) - 1
    lines = [f"select {', '.join(select)}", f"from {fact.table} as {fact.alias}", *joins]
    if where:
        lines.append("where " + " and ".join(where))
    if group_count:
        lines.append("group by " + ", ".join(str(i) for i in range(1, group_count + 1)))
        order = "1" if request.grain is not None else f"{len(columns)} desc nulls last"
        lines.append(f"order by {order}")
    lines.append("limit %(row_limit)s")
    params["row_limit"] = request.limit
    if metric.unit == "NZD":
        assumptions.append("amounts in NZD (AUD converted at the monthly rate)")

    return CompiledQuery(
        metric=request.metric,
        sql="\n".join(lines),
        params=params,
        columns=columns,
        time_range=resolved,
        assumptions=assumptions,
    )

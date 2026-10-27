"""The agent's read-only tools (spec §8.2). Each one runs as the caller's persona login.

A tool never raises for a problem the model could react to. It returns a ToolResult:
- `ok` with rows (and the SQL that produced them, for "Show SQL");
- `denied` when the semantic layer or Postgres refused on access grounds, naming the mechanism
  so the answer can explain it (access denial reads as a feature, spec §10);
- `rejected` when the SQL guard refused the query;
- `error` for anything else the model might fix (unknown column, bad metric name, timeout).

Results are kept on the ToolContext by id, so the final answer can reference a table by id
instead of retyping numbers.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import psycopg
from pydantic import BaseModel, Field

from app.agent.db import PersonaPools
from app.agent.personas import Persona
from app.agent.sql_guard import MAX_ROWS, SqlRejected, guard_sql
from app.retrieval.search import MAX_K, DocChunk, hybrid_search
from app.semantic.compiler import (
    MetricNotAllowed,
    SemanticError,
    compile_metric,
    load_semantic_model,
)
from app.semantic.models import MetricRequest

Status = Literal["ok", "denied", "rejected", "error"]


class ToolResult(BaseModel):
    result_id: str
    tool: str
    status: Status
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    sql: str | None = None
    params: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    chunks: list[DocChunk] = Field(default_factory=list)
    message: str | None = None
    denied_by: str | None = None


class ListMetricsInput(BaseModel):
    pass


class RunSqlInput(BaseModel):
    sql: str = Field(description="One read-only SELECT over the marts schema.")


class DescribeTablesInput(BaseModel):
    tables: list[str] | None = Field(
        default=None, description="Mart table names; omit to list every table you can read."
    )


class SearchDocumentsInput(BaseModel):
    query: str = Field(description="What to look for in company policy documents.")
    k: int = Field(default=5, ge=1, le=MAX_K, description="Number of passages to return.")


@dataclass
class ToolContext:
    persona: Persona
    pools: PersonaPools
    embed_query: Callable[[str], list[float]]
    today: date = field(default_factory=date.today)
    results: dict[str, ToolResult] = field(default_factory=dict)

    def new_result(self, tool: str, status: Status, **fields: Any) -> ToolResult:
        result = ToolResult(
            result_id=f"r{len(self.results) + 1}", tool=tool, status=status, **fields
        )
        self.results[result.result_id] = result
        return result


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _run_query(
    ctx: ToolContext, tool: str, sql: str, params: dict[str, Any] | None, **fields: Any
) -> ToolResult:
    """Run SQL as the persona and map database errors to results the model can use."""
    try:
        with ctx.pools.transaction(ctx.persona.id) as conn:
            cursor = conn.execute(sql, params)
            columns = [column.name for column in cursor.description or []]
            rows = [[_json_value(v) for v in row] for row in cursor.fetchmany(MAX_ROWS)]
    except psycopg.errors.InsufficientPrivilege as error:
        return ctx.new_result(
            tool,
            "denied",
            sql=sql,
            params=params,
            denied_by="database privileges (column or table grant)",
            message=(
                f"Postgres refused this query for the {ctx.persona.title.lower()} role: "
                f"{error.diag.message_primary}. The data exists but this role may not see it."
            ),
            **fields,
        )
    except psycopg.errors.QueryCanceled:
        return ctx.new_result(
            tool, "error", sql=sql, params=params, message="query timed out (8 s)", **fields
        )
    except psycopg.Error as error:
        message = error.diag.message_primary or str(error)
        return ctx.new_result(tool, "error", sql=sql, params=params, message=message, **fields)
    return ctx.new_result(
        tool,
        "ok",
        columns=columns,
        rows=rows,
        row_count=len(rows),
        sql=sql,
        params=params,
        **fields,
    )


def list_metrics(ctx: ToolContext, _: ListMetricsInput) -> ToolResult:
    """Metrics this role may use, with the dimensions each one supports. No database call."""
    model = load_semantic_model()
    rows = [
        [
            name,
            metric.description,
            metric.unit,
            ", ".join(d for d, dim in model.dimensions.items() if metric.model in dim.expressions),
        ]
        for name, metric in model.metrics.items()
        if ctx.persona.role in metric.roles
    ]
    return ctx.new_result(
        "list_metrics",
        "ok",
        columns=["metric", "description", "unit", "dimensions"],
        rows=rows,
        row_count=len(rows),
        message="time_range: a preset (last_7_days, last_30_days, this_month, last_month,"
        " this_quarter, last_quarter, ytd, last_year, last_12_months) or"
        " YYYY-MM-DD..YYYY-MM-DD; grain: day, week, month, quarter or year.",
    )


def get_metric(ctx: ToolContext, request: MetricRequest) -> ToolResult:
    try:
        compiled = compile_metric(request, ctx.persona.role, today=ctx.today)
    except MetricNotAllowed as error:
        return ctx.new_result(
            "get_metric", "denied", denied_by="semantic layer role check", message=str(error)
        )
    except SemanticError as error:
        return ctx.new_result("get_metric", "error", message=str(error))
    return _run_query(
        ctx,
        "get_metric",
        compiled.sql,
        compiled.params,
        assumptions=compiled.assumptions,
    )


def run_sql(ctx: ToolContext, request: RunSqlInput) -> ToolResult:
    try:
        guarded = guard_sql(request.sql)
    except SqlRejected as error:
        return ctx.new_result(
            "run_sql", "rejected", sql=request.sql, denied_by="SQL guard", message=str(error)
        )
    return _run_query(ctx, "run_sql", guarded.sql, None)


def describe_tables(ctx: ToolContext, request: DescribeTablesInput) -> ToolResult:
    # information_schema.columns lists only columns the current login holds a privilege on,
    # so hidden columns (e.g. margin for sales) never appear.
    sql = (
        "select table_name, column_name, data_type from information_schema.columns"
        " where table_schema = 'marts'"
        + (" and table_name = any(%(tables)s)" if request.tables else "")
        + " order by table_name, ordinal_position"
    )
    params = {"tables": request.tables} if request.tables else None
    return _run_query(ctx, "describe_tables", sql, params)


def search_documents(ctx: ToolContext, request: SearchDocumentsInput) -> ToolResult:
    try:
        embedding = ctx.embed_query(request.query)
        with ctx.pools.transaction(ctx.persona.id) as conn:
            chunks = hybrid_search(conn, request.query, embedding, request.k)
    except psycopg.Error as error:
        return ctx.new_result("search_documents", "error", message=str(error))
    except Exception as error:  # embedding provider failures must not crash the loop
        return ctx.new_result(
            "search_documents", "error", message=f"document search unavailable: {error}"
        )
    return ctx.new_result(
        "search_documents",
        "ok",
        columns=["chunk_id", "document", "section"],
        rows=[[c.chunk_id, c.doc_title, c.section] for c in chunks],
        row_count=len(chunks),
        chunks=chunks,
    )


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[ToolContext, Any], ToolResult]


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            "list_metrics",
            "List the business metrics and dimensions available to the current user's role.",
            ListMetricsInput,
            list_metrics,
        ),
        ToolSpec(
            "get_metric",
            "Compute a named metric, optionally by dimensions, filters and time range."
            " Preferred over run_sql for anything list_metrics covers.",
            MetricRequest,
            get_metric,
        ),
        ToolSpec(
            "run_sql",
            "Run one read-only Postgres SELECT over the marts schema (max 1,000 rows)."
            " Use only when get_metric cannot answer. Call describe_tables first.",
            RunSqlInput,
            run_sql,
        ),
        ToolSpec(
            "describe_tables",
            "List mart tables and the columns the current user's role may read.",
            DescribeTablesInput,
            describe_tables,
        ),
        ToolSpec(
            "search_documents",
            "Search company policy documents (pricing, returns, warranty, credit, SLAs,"
            " playbooks, regional guides) the current user's role may read.",
            SearchDocumentsInput,
            search_documents,
        ),
    )
}


def call_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> ToolResult:
    """Validate the model's arguments and run the tool. Unknown tools and bad input are errors."""
    spec = TOOLS.get(name)
    if spec is None:
        return ctx.new_result(name, "error", message=f"unknown tool {name!r}")
    try:
        request = spec.input_model.model_validate(arguments)
    except ValueError as error:
        return ctx.new_result(name, "error", message=f"invalid input: {error}")
    return spec.run(ctx, request)

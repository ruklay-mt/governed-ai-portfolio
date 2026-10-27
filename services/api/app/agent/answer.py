"""Build the answer card from the model's final JSON and the stored tool results.

The model never retypes numbers: it points at a tool result by id, and the table comes from
that result's rows. Anything the model references that was not actually retrieved (an unknown
result id, a chart column that is not in the table, a chunk it never saw) is dropped and noted
in `issues`, so the card only ever shows evidence that exists.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.tools import ToolResult


class Table(BaseModel):
    result_id: str
    columns: list[str]
    rows: list[list[Any]]


class Chart(BaseModel):
    type: Literal["bar", "line"]
    x: str
    y: str


class Citation(BaseModel):
    chunk_id: str
    doc_title: str
    section: str
    source: str


class SqlEvidence(BaseModel):
    result_id: str
    tool: str
    sql: str
    params: dict[str, Any] | None = None


class Denial(BaseModel):
    result_id: str
    tool: str
    denied_by: str
    message: str


class Answer(BaseModel):
    text: str
    assumptions: list[str] = Field(default_factory=list)
    table: Table | None = None
    chart: Chart | None = None
    citations: list[Citation] = Field(default_factory=list)
    sql: list[SqlEvidence] = Field(default_factory=list)
    denials: list[Denial] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class ModelAnswer(BaseModel):
    """The final_answer tool input (prompts.ANSWER_SCHEMA)."""

    text: str
    assumptions: list[str]
    table_result_id: str
    table_rows: int = 0
    chart: dict[str, str]
    citations: list[str]


def evidence(results: dict[str, ToolResult]) -> tuple[list[SqlEvidence], list[Denial]]:
    sql = [
        SqlEvidence(result_id=r.result_id, tool=r.tool, sql=r.sql, params=r.params)
        for r in results.values()
        if r.sql is not None and r.tool in ("get_metric", "run_sql")
    ]
    denials = [
        Denial(
            result_id=r.result_id,
            tool=r.tool,
            denied_by=r.denied_by or "unknown",
            message=r.message or "",
        )
        for r in results.values()
        if r.status in ("denied", "rejected")
    ]
    return sql, denials


def assemble_answer(model_answer: ModelAnswer, results: dict[str, ToolResult]) -> Answer:
    issues: list[str] = []

    table: Table | None = None
    if model_answer.table_result_id:
        result = results.get(model_answer.table_result_id)
        if result is None or result.status != "ok" or result.tool == "search_documents":
            issues.append(f"table_result_id {model_answer.table_result_id!r} is not a data result")
        elif result.rows:
            rows = (
                result.rows[: model_answer.table_rows]
                if model_answer.table_rows > 0
                else result.rows
            )
            table = Table(result_id=result.result_id, columns=result.columns, rows=rows)

    chart: Chart | None = None
    chart_type = model_answer.chart.get("type", "none")
    if chart_type in ("bar", "line") and table is not None:
        x, y = model_answer.chart.get("x", ""), model_answer.chart.get("y", "")
        if x in table.columns and y in table.columns:
            chart = Chart(type=chart_type, x=x, y=y)
        else:
            issues.append(f"chart columns {x!r}/{y!r} are not in the table")

    retrieved = {
        chunk.chunk_id: chunk
        for result in results.values()
        if result.status == "ok"
        for chunk in result.chunks
    }
    citations: list[Citation] = []
    for chunk_id in dict.fromkeys(model_answer.citations):
        chunk = retrieved.get(chunk_id)
        if chunk is None:
            issues.append(f"citation {chunk_id!r} was not retrieved")
            continue
        citations.append(
            Citation(
                chunk_id=chunk.chunk_id,
                doc_title=chunk.doc_title,
                section=chunk.section,
                source=chunk.source,
            )
        )

    sql, denials = evidence(results)
    assumptions = list(dict.fromkeys(model_answer.assumptions))
    return Answer(
        text=model_answer.text,
        assumptions=assumptions,
        table=table,
        chart=chart,
        citations=citations,
        sql=sql,
        denials=denials,
        issues=issues,
    )

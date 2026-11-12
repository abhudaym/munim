"""question -> model -> guard -> read-only run -> answer. Retries once with the error."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from munim.ask.charts import choose_chart
from munim.ask.context import build_context
from munim.ask.dashboard import is_rolling, to_template
from munim.ask.guard import GuardError, check_sql
from munim.ask.llm import LLMError, SQLWriter
from munim.ask.runner import QueryError, QueryResult, connect_readonly, run_query
from munim.db.models import Question

MAX_ATTEMPTS = 2


@dataclass
class AskResult:
    question: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    note: str | None = None  # the model's one-line reading of the question
    error: str | None = None
    attempts: int = 0
    headline: float | int | None = None  # set when the answer is one number
    model: str | None = None
    chart: str = "table"  # suggested drawing for this shape of result
    charts: list[str] = field(default_factory=lambda: ["table"])
    value_col: int | None = None
    time: bool = False
    rolling: bool = False  # the dates are relative to today, so a pinned tile can keep moving

    def to_dict(self) -> dict:
        return asdict(self)


def _headline(result: QueryResult) -> float | int | None:
    if len(result.rows) == 1 and len(result.columns) == 1:
        value = result.rows[0][0]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return round(value, 2) if isinstance(value, float) else value
    return None


def ask(
    question: str,
    *,
    db_path: str | Path,
    llm: SQLWriter,
    session_factory: sessionmaker[Session] | None = None,
    today: date | None = None,
    log: bool = True,
) -> AskResult:
    out = AskResult(question=" ".join(question.split()), model=llm.name)
    today = today or date.today()
    llm_error: LLMError | None = None

    conn = connect_readonly(db_path)
    try:
        context = build_context(conn, today)
        previous: tuple[str, str] | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            out.attempts = attempt
            draft = llm.write_query(out.question, context, previous)
            out.note = draft.note
            if draft.sql is None:  # the model says this can't be answered from the data
                out.sql, out.error = None, None
                break
            out.sql = draft.sql
            try:
                out.sql = check_sql(draft.sql)
                result = run_query(conn, out.sql)
            except (GuardError, QueryError) as exc:
                out.error = str(exc)
                previous = (draft.sql, out.error)
                continue
            out.error = None
            out.columns, out.rows, out.truncated = result.columns, result.rows, result.truncated
            out.headline = _headline(result)
            choice = choose_chart(result.columns, result.rows)
            out.chart, out.charts, out.value_col, out.time = choice.chart, choice.charts, choice.value_col, choice.time
            out.rolling = is_rolling(to_template(out.sql, today))
            break
    except LLMError as exc:
        llm_error = exc
        out.error = str(exc)
    finally:
        conn.close()

    if log and session_factory is not None:
        with session_factory() as session:
            session.add(
                Question(
                    question=out.question,
                    sql=out.sql,
                    row_count=len(out.rows) if out.error is None and out.sql else None,
                    error=out.error,
                    attempts=out.attempts,
                    model=out.model,
                )
            )
            session.commit()

    if llm_error is not None:
        raise llm_error
    return out

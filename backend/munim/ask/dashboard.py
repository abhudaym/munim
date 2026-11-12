"""Pinned questions. A tile stores a query, never its numbers; it is re-run each time it is shown."""

from __future__ import annotations

import re
import sqlite3
from datetime import date

from munim.ask.charts import choose_chart
from munim.ask.context import date_tokens
from munim.ask.guard import GuardError, check_sql
from munim.ask.runner import QueryError, run_query

# When two windows start on the same day (1 January is both month_start and year_start),
# the earlier name here wins.
_PRIORITY = (
    "month_start",
    "year_start",
    "last_month_start",
    "last_month_end",
    "today",
    "three_months_ago",
    "six_months_ago",
    "twelve_months_ago",
    "days_30_ago",
)
_LITERAL = re.compile(r"'(\d{4}-\d{2}-\d{2})'")
_PLACEHOLDER = re.compile(r"'\{(\w+)\}'")


def to_template(sql: str, today: date) -> str:
    """Swap date literals that match a known window for '{token}', so the tile keeps rolling."""
    tokens = date_tokens(today)
    by_value: dict[str, str] = {}
    for name in _PRIORITY:
        by_value.setdefault(tokens[name], name)
    return _LITERAL.sub(lambda m: f"'{{{by_value[m.group(1)]}}}'" if m.group(1) in by_value else m.group(0), sql)


def is_rolling(template: str) -> bool:
    return bool(_PLACEHOLDER.search(template))


def render(template: str, today: date) -> str:
    tokens = date_tokens(today)
    return _PLACEHOLDER.sub(lambda m: f"'{tokens[m.group(1)]}'" if m.group(1) in tokens else m.group(0), template)


def run_tile(conn: sqlite3.Connection, template: str, chart: str, today: date) -> dict:
    """Run one tile through the same guard and read-only runner as a fresh question."""
    out = {"columns": [], "rows": [], "truncated": False, "error": None, "chart": chart, "charts": ["table"], "value_col": None, "time": False}
    try:
        result = run_query(conn, check_sql(render(template, today)))
    except (GuardError, QueryError) as exc:
        out["error"] = str(exc)
        return out
    choice = choose_chart(result.columns, result.rows)
    out.update(
        columns=result.columns,
        rows=result.rows,
        truncated=result.truncated,
        charts=choice.charts,
        value_col=choice.value_col,
        time=choice.time,
    )
    if chart not in choice.charts:  # the data changed shape since it was pinned
        out["chart"] = choice.chart
    return out

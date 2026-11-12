"""Pick a chart from the shape of a result. Plain rules, so the same shape always draws the same way."""

from __future__ import annotations

import re
from dataclasses import dataclass

CHARTS = ("number", "bars", "line", "table")
MAX_BARS = 30  # more marks than this stops being readable
MANY = 12  # a ranked list longer than this reads better as a table
MAX_POINTS = 120  # a line can carry this many points (ten years of months)
MAX_SERIES = 6  # colours that stay tell-apart-able

_TIME = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
_MONEY = re.compile(r"(amount|total|spent|spend|sum|avg|average|income|expense|max|min|cost)", re.I)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass
class ChartChoice:
    chart: str  # the suggestion
    charts: list[str]  # everything that fits this shape, suggestion first
    value_col: int | None  # column drawn as the mark; labels are always column 0
    time: bool  # labels are months or dates, so order matters and a line makes sense
    plot: dict | None = None  # multi-series only: {"labels": [...], "series": [{"name", "values"}]}


def _multi_series(columns: list[str], rows: list[list]) -> ChartChoice | None:
    """Several lines over time: (month, name, value) rows, or (month, value, value, ...) columns."""
    if len(columns) < 3 or len(rows) < 3 or len(rows) > MAX_POINTS * MAX_SERIES:
        return None
    if not all(isinstance(r[0], str) and _TIME.match(r[0]) for r in rows):
        return None
    if all(isinstance(r[1], str) or r[1] is None for r in rows) and len(columns) == 3:
        value = 2
        if not all(_is_number(r[value]) or r[value] is None for r in rows):
            return None
        names = list(dict.fromkeys(r[1] if r[1] is not None else "none" for r in rows))
        cells: dict[tuple, float] = {}
        for r in rows:
            key = (r[0], r[1] if r[1] is not None else "none")
            cells[key] = cells.get(key, 0) + (r[value] or 0)
        if len(cells) != len(rows):
            return None  # repeated (time, name) pairs are not a series
        labels = sorted({r[0] for r in rows})
        series = [{"name": n, "values": [cells.get((lab, n), 0) for lab in labels]} for n in names]
        money_col = columns[value]
    else:
        numeric = list(range(1, len(columns)))
        if not all(_is_number(r[i]) or r[i] is None for r in rows for i in numeric):
            return None
        if len({r[0] for r in rows}) != len(rows):
            return None
        ordered = sorted(rows, key=lambda r: r[0])
        labels = [r[0] for r in ordered]
        series = [{"name": columns[i], "values": [r[i] or 0 for r in ordered]} for i in numeric]
        money_col = columns[1]
    if not 2 <= len(series) <= MAX_SERIES or len(labels) < 2 or len(labels) > MAX_POINTS:
        return None
    if any(v < 0 for s in series for v in s["values"]):
        return None
    return ChartChoice("line", ["line", "table"], None, True, {"labels": labels, "series": series, "column": money_col})


def choose_chart(columns: list[str], rows: list[list]) -> ChartChoice:
    table = ChartChoice("table", ["table"], None, False)
    if not rows or not columns:
        return table
    if len(rows) == 1 and len(columns) == 1:
        return ChartChoice("number", ["number", "table"], 0, False) if _is_number(rows[0][0]) else table
    multi = _multi_series(columns, rows)
    if multi:
        return multi
    labels = [r[0] for r in rows]
    is_time = bool(labels) and all(isinstance(v, str) and _TIME.match(v) for v in labels)
    if len(columns) < 2 or len(rows) < 2 or len(rows) > (MAX_POINTS if is_time else MAX_BARS):
        return table
    if not all(isinstance(v, str) for v in labels) or len(set(labels)) != len(labels):
        return table
    # A second text column means these are individual entries, not one value per label.
    if any(isinstance(r[i], str) for r in rows for i in range(1, len(columns))):
        return table

    numeric = [
        i
        for i in range(1, len(columns))
        if any(_is_number(r[i]) for r in rows) and all(_is_number(r[i]) or r[i] is None for r in rows)
    ]
    if not numeric:
        return table
    value_col = next((i for i in numeric if _MONEY.search(columns[i])), numeric[0])
    if any((r[value_col] or 0) < 0 for r in rows):
        return table

    if all(_TIME.match(v) for v in labels):
        if len(rows) > MAX_BARS:
            return ChartChoice("line", ["line", "table"], value_col, True)
        return ChartChoice("bars", ["bars", "line", "table"], value_col, True)
    if len(rows) > MANY:
        return ChartChoice("table", ["table", "bars"], value_col, False)
    return ChartChoice("bars", ["bars", "table"], value_col, False)

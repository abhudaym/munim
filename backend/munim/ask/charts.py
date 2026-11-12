"""Pick a chart from the shape of a result. Plain rules, so the same shape always draws the same way."""

from __future__ import annotations

import re
from dataclasses import dataclass

CHARTS = ("number", "bars", "line", "table")
MAX_BARS = 30  # more marks than this stops being readable
MANY = 12  # a ranked list longer than this reads better as a table

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


def choose_chart(columns: list[str], rows: list[list]) -> ChartChoice:
    table = ChartChoice("table", ["table"], None, False)
    if not rows or not columns:
        return table
    if len(rows) == 1 and len(columns) == 1:
        return ChartChoice("number", ["number", "table"], 0, False) if _is_number(rows[0][0]) else table
    if len(columns) < 2 or len(rows) < 2 or len(rows) > MAX_BARS:
        return table
    labels = [r[0] for r in rows]
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
        return ChartChoice("bars", ["bars", "line", "table"], value_col, True)
    if len(rows) > MANY:
        return ChartChoice("table", ["table", "bars"], value_col, False)
    return ChartChoice("bars", ["bars", "table"], value_col, False)

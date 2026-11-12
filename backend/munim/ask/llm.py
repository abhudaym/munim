"""The model that writes SQL. Behind a small interface so tests (and evals) can swap it."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"

SYSTEM = """You turn one question about a person's finances into one read-only SQLite query. \
Always answer by calling the write_query tool.

Rules:
- Use v_expenses for anything about spending. Use v_entries only for income, investments, transfers \
or "everything", and then filter kind explicitly.
- Dates are text 'YYYY-MM-DD'. Filter with txn_date >= 'a' AND txn_date <= 'b', copying the \
ready-made dates from the context. "this month" = month_start..today. "last month" = \
last_month_start..last_month_end. "this year" = year_start..today. "last 3/6/12 months" = \
three_months_ago / six_months_ago / twelve_months_ago .. today. "last 30 days" = days_30_ago..today. \
Never use date('now') or arithmetic on today. For a named month use that month's literal first and last \
day, in the latest year that has data for it.
- category must match a listed name exactly. subcategory and merchant are lowercase; match merchant with \
LIKE '%text%' in lowercase. Words like coffee, eating out and delivery are subcategories (coffee, eatout, \
delivery) when they are listed.
- Totals use SUM(amount). Name money columns spent, total or amount, and counts n.
- Return only what was asked: one number for "how much" or "how many"; a short ranked list (10 rows unless \
told otherwise) for "top" or "biggest"; a month column, ordered by month, for per-month breakdowns.
- One statement. No comments. SQLite syntax only.
- If the question cannot be answered from these views (balances, net worth, market value of investments, \
dates outside the data), set sql to an empty string and explain in note.
- note: one short sentence saying what the query measures and the exact date range, so the person can spot \
a misreading."""

TOOL = {
    "name": "write_query",
    "description": "Return the SQL that answers the question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "The SELECT query, or an empty string if it cannot be answered."},
            "note": {"type": "string", "description": "One short sentence: what it measures and the date range used."},
        },
        "required": ["sql", "note"],
    },
}


class LLMError(RuntimeError):
    """The model call failed. Nothing to retry on our side."""


@dataclass
class Draft:
    sql: str | None  # None: the model says it cannot answer
    note: str | None


class SQLWriter(Protocol):
    name: str

    def write_query(self, question: str, context: str, previous: tuple[str, str] | None = None) -> Draft: ...


class AnthropicSQLWriter:
    def __init__(self, client=None, model: str | None = None):
        import anthropic

        self._anthropic = anthropic
        self.client = client or anthropic.Anthropic(timeout=30.0)
        self.name = model or os.environ.get("MUNIM_MODEL") or DEFAULT_MODEL

    @classmethod
    def from_env(cls) -> AnthropicSQLWriter | None:
        return cls() if os.environ.get("ANTHROPIC_API_KEY") else None

    def write_query(self, question: str, context: str, previous: tuple[str, str] | None = None) -> Draft:
        prompt = f"{context}\n\nQuestion: {question}"
        if previous:
            sql, error = previous
            prompt += f"\n\nYour previous query failed.\nQuery:\n{sql}\nError: {error}\nWrite a corrected query."

        try:
            response = self.client.messages.create(
                model=self.name,
                max_tokens=1024,
                system=SYSTEM,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": TOOL["name"]},
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as exc:
            raise LLMError(f"The model call failed: {type(exc).__name__}: {exc}") from exc

        block = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
        if block is None:
            raise LLMError("The model did not return a query.")
        data = block.input or {}
        sql = (data.get("sql") or "").strip()
        note = (data.get("note") or "").strip() or None
        return Draft(sql=sql or None, note=note)

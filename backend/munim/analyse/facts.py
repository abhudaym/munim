"""The fact pack: the same handful of numbers for every analysis, computed in code.

Everything reads the Ask views through the read-only runner, so this module can see exactly what
Ask can see and nothing more.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from munim.ask.context import date_tokens, months_ago
from munim.ask.runner import run_query

WINDOW_MONTHS = 6
TOP_CATEGORIES = 5
YARDSTICK_SAVE_PCT = 20.0  # the common "save at least a fifth" rule of thumb


@dataclass
class Fact:
    key: str
    label: str
    value: float | None = None  # None for text-only facts
    unit: str = "inr"  # inr | pct | months | count | text | table
    text: str = ""  # how it is shown to the model and the person
    numbers: list[float] = field(default_factory=list)  # every number a table/text fact contains

    def line(self) -> str:
        return f"{self.label}: {self.text}"


@dataclass
class Goal:
    amount: float
    months: int
    label: str | None = None


def inr(value: float) -> str:
    """Rupees with Indian grouping: 1,23,456. Whole rupees; amounts here are averages, not ledgers."""
    n = round(value)
    sign = "-" if n < 0 else ""
    digits = str(abs(n))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"{sign}₹{digits}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def _fmt(value: float, unit: str) -> str:
    if unit == "inr":
        return inr(value)
    if unit == "pct":
        return pct(value)
    if unit == "months":
        return f"{value:.1f} months"
    return f"{value:g}"


def _fact(key: str, label: str, value: float, unit: str = "inr") -> Fact:
    value = round(value, 1) if unit in ("pct", "months") else round(value)
    return Fact(key=key, label=label, value=value, unit=unit, text=_fmt(value, unit))


def _month_name(month: str) -> str:
    y, m = month.split("-")
    return date(int(y), int(m), 1).strftime("%b %Y")


def _rows(conn: sqlite3.Connection, sql: str, *params) -> list[list]:
    # run_query takes no parameters: every value here is a date or a constant built in this module.
    assert not params
    return run_query(conn, sql).rows


_MONTHLY = """
SELECT month,
       SUM(CASE WHEN kind = 'income' THEN amount ELSE 0 END),
       SUM(CASE WHEN kind = 'expense' THEN amount ELSE 0 END),
       SUM(CASE WHEN kind = 'transfer' AND LOWER(category) = 'investments' THEN amount ELSE 0 END),
       SUM(CASE WHEN kind = 'transfer' AND LOWER(category) = 'emi' THEN amount ELSE 0 END)
FROM v_entries WHERE txn_date >= '{start}' AND txn_date <= '{end}'
GROUP BY month ORDER BY month
"""


def fact_pack(conn: sqlite3.Connection, today: date, goal: Goal | None = None) -> list[Fact]:
    t = date_tokens(today)
    start, end = t["six_full_months_start"], t["last_month_end"]
    prev_start = months_ago(date.fromisoformat(start), WINDOW_MONTHS).isoformat()

    months = _rows(conn, _MONTHLY.format(start=start, end=end))
    facts: list[Fact] = []
    if not months:  # nothing in the last six whole months: fall back to everything there is
        months = _rows(conn, _MONTHLY.format(start="0000-01-01", end=today.isoformat()))
        if not months:
            return [Fact("empty", "Data", unit="text", text="No entries have been imported yet.")]
        start = f"{months[0][0]}-01"
    n = len(months)
    facts.append(
        Fact(
            "period", "Period used for averages", unit="text",
            text=f"{_month_name(months[0][0])} to {_month_name(months[-1][0])} ({n} whole month{'s' if n != 1 else ''})",
            numbers=[float(n)],
        )
    )

    income = sum(r[1] or 0 for r in months) / n
    spent = sum(r[2] or 0 for r in months) / n
    invested = sum(r[3] or 0 for r in months) / n
    emi = sum(r[4] or 0 for r in months) / n
    left = income - spent - invested - emi
    facts += [
        _fact("avg_income", "Average monthly income", income),
        _fact("avg_spent", "Average monthly spending", spent),
        _fact("avg_invested", "Average monthly investments", invested),
        _fact("avg_emi", "Average monthly EMIs", emi),
        _fact("avg_left", "Average left over each month after spending, investments and EMIs", left),
    ]
    if income > 0:
        facts += [
            _fact("spend_share", "Spending as a share of income", spent / income * 100, "pct"),
            _fact("invest_share", "Investments as a share of income", invested / income * 100, "pct"),
            _fact("emi_share", "EMIs as a share of income", emi / income * 100, "pct"),
            _fact("save_rate", "Saved or invested, as a share of income (income minus spending and EMIs)",
                  (income - spent - emi) / income * 100, "pct"),
        ]
    else:
        facts.append(Fact("no_income", "Income", unit="text", text="No income was recorded in this period."))
    facts.append(_fact("yardstick", "Common rule of thumb: save or invest at least this share of income",
                       YARDSTICK_SAVE_PCT, "pct"))

    if n >= 2:
        hi = max(months, key=lambda r: r[2] or 0)
        lo = min(months, key=lambda r: r[2] or 0)
        facts += [
            Fact("high_month", "Highest spending month", hi[2], "inr",
                 f"{_month_name(hi[0])}, {inr(hi[2] or 0)}", [round(hi[2] or 0)]),
            Fact("low_month", "Lowest spending month", lo[2], "inr",
                 f"{_month_name(lo[0])}, {inr(lo[2] or 0)}", [round(lo[2] or 0)]),
        ]

    prev = _rows(conn, _MONTHLY.format(start=prev_start, end=_day_before(start)))
    if prev:
        prev_spent = sum(r[2] or 0 for r in prev) / len(prev)
        facts.append(_fact("prev_avg_spent", f"Average monthly spending in the {len(prev)} months before that", prev_spent))
        if prev_spent > 0:
            change = _fact("spent_change", "Change in average monthly spending against those months",
                           (spent - prev_spent) / prev_spent * 100, "pct")
            change.text = ("+" if change.value >= 0 else "") + change.text
            facts.append(change)

    cats = _rows(
        conn,
        f"SELECT category, SUM(amount) FROM v_expenses WHERE txn_date >= '{start}' AND txn_date <= '{end}' "
        f"GROUP BY category ORDER BY 2 DESC LIMIT {TOP_CATEGORIES}",
    )
    if cats:
        prev_cats = dict(
            _rows(
                conn,
                f"SELECT category, SUM(amount) FROM v_expenses WHERE txn_date >= '{prev_start}' "
                f"AND txn_date < '{start}' GROUP BY category",
            )
        )
        lines, numbers = [], []
        for name, total in cats:
            avg = total / n
            part = f"{name} {inr(avg)} a month"
            numbers.append(round(avg))
            if spent > 0:
                share = round(avg / spent * 100, 1)
                part += f" ({pct(share)} of spending"
                numbers.append(share)
                before = prev_cats.get(name)
                if prev and before:
                    change = round((avg - before / len(prev)) / (before / len(prev)) * 100, 1)
                    part += f", {'+' if change >= 0 else ''}{pct(change)} against the months before"
                    numbers.append(change)
                part += ")"
            lines.append(part)
        facts.append(Fact("top_categories", "Biggest spending categories, monthly average", unit="table",
                          text="; ".join(lines), numbers=numbers))

    so_far = _rows(conn, f"SELECT SUM(amount) FROM v_expenses WHERE txn_date >= '{t['month_start']}' AND txn_date <= '{t['today']}'")
    facts.append(Fact("month_so_far", f"Spent so far this month ({today.day} days in)", so_far[0][0] or 0, "inr",
                      inr(so_far[0][0] or 0), [float(today.day)]))

    worth = _rows(conn, "SELECT SUM(value), MAX(as_of), COUNT(*) FROM v_holdings")[0]
    if worth[2]:
        facts.append(Fact("net_worth", "Net worth (latest value of each account, typed in by hand)", worth[0], "inr",
                          f"{inr(worth[0])}, newest entry {worth[1]}"))
    unpaid = _rows(conn, "SELECT SUM(amount), COUNT(*) FROM v_bills WHERE is_paid = 0")[0]
    if unpaid[1]:
        facts.append(Fact("unpaid_bills", "Unpaid credit card bills", unpaid[0], "inr",
                          f"{inr(unpaid[0])} across {unpaid[1]} bill{'s' if unpaid[1] != 1 else ''}", [float(unpaid[1])]))

    if goal:
        facts += goal_facts(goal, left, invested)
    return facts


def goal_facts(goal: Goal, left: float, invested: float = 0.0) -> list[Fact]:
    name = goal.label or "the goal"
    out = [
        _fact("goal_amount", f"Cost of {name}", goal.amount),
        Fact("goal_months", "Months until it is needed", goal.months, "count", f"{goal.months}"),
        _fact("goal_per_month", f"Needed each month to afford {name} in time", goal.amount / goal.months),
    ]
    gap = goal.amount / goal.months - left
    if gap > 0:
        out.append(_fact("goal_gap", "Shortfall each month against what is left over now", gap))
    else:
        out.append(_fact("goal_spare", "Left over each month beyond what the goal needs", -gap))
    if left > 0:
        out.append(_fact("goal_months_now", "Months to save it at the current left-over rate", goal.amount / left, "months"))
    else:
        out.append(Fact("goal_never", "At the current left-over rate", unit="text",
                        text="nothing is left over each month, so it cannot be saved without changes"))
    if invested > 0 and left + invested > 0:
        out.append(_fact("goal_months_with_investing",
                         "Months to save it if the monthly investments went to it as well", goal.amount / (left + invested), "months"))
    return out


def _day_before(iso: str) -> str:
    from datetime import timedelta

    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()

"""The text the model gets about your data. Names and counts only: never amounts, never rows."""

from __future__ import annotations

import calendar
import os
import sqlite3
from datetime import date, timedelta

from munim.db.views import COLUMNS

MIN_MERCHANT_USES = 3
MAX_MERCHANTS = 40
MAX_SUBCATEGORIES = 30


def months_ago(d: date, n: int) -> date:
    year, month0 = divmod(d.year * 12 + d.month - 1 - n, 12)
    month = month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def date_tokens(today: date) -> dict[str, str]:
    """Pre-computed windows, so the model copies dates instead of doing calendar maths."""
    first = today.replace(day=1)
    last_month_end = first - timedelta(days=1)
    return {
        "today": today.isoformat(),
        "month_start": first.isoformat(),
        "last_month_start": last_month_end.replace(day=1).isoformat(),
        "last_month_end": last_month_end.isoformat(),
        "year_start": today.replace(month=1, day=1).isoformat(),
        "days_30_ago": (today - timedelta(days=30)).isoformat(),
        "three_months_ago": months_ago(today, 3).isoformat(),
        "six_months_ago": months_ago(today, 6).isoformat(),
        "twelve_months_ago": months_ago(today, 12).isoformat(),
        # whole calendar months, ending at last_month_end
        "three_full_months_start": months_ago(first, 3).isoformat(),
        "six_full_months_start": months_ago(first, 6).isoformat(),
        "twelve_full_months_start": months_ago(first, 12).isoformat(),
    }


def send_merchants_enabled() -> bool:
    return os.environ.get("MUNIM_SEND_MERCHANTS", "1") != "0"


def build_context(conn: sqlite3.Connection, today: date, send_merchants: bool | None = None) -> str:
    if send_merchants is None:
        send_merchants = send_merchants_enabled()
    q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731

    first, last, n = q("SELECT min(txn_date), max(txn_date), count(*) FROM v_entries")[0]
    categories = q("SELECT category, kind, count(*) FROM v_entries GROUP BY category, kind ORDER BY 3 DESC")
    subs = q(
        "SELECT subcategory, count(*) FROM v_entries WHERE subcategory IS NOT NULL "
        f"GROUP BY 1 ORDER BY 2 DESC LIMIT {MAX_SUBCATEGORIES}"
    )

    lines = [
        f"Today is {today.strftime('%A')} {today.isoformat()}.",
        f"The data covers {first} to {last} ({n} entries).",
        "",
        "Views (use these names exactly; there are no other tables):",
        "  v_expenses: money spent. Use this for any question about spending.",
        "  v_entries: every entry including income and transfers (SIPs, investments, EMIs).",
        "Columns, identical in both:",
        *[f"  {name}: {desc}" for name, desc in COLUMNS],
        "",
        "Ready-made dates (copy these as literals, never use 'now' or date functions on today):",
        *[f"  {k} = {v}" for k, v in date_tokens(today).items()],
        "",
        "Categories as 'name (kind, entries)':",
        "  " + ", ".join(f"{c} ({k}, {cnt})" for c, k, cnt in categories),
    ]
    odo_n, odo_first, odo_last = q(
        "SELECT count(*), min(txn_date), max(txn_date) FROM v_entries WHERE odometer_km IS NOT NULL"
    )[0]
    if odo_n:
        lines += ["", f"Odometer readings: {odo_n} entries, from {odo_first} to {odo_last}. None outside those dates."]
    else:
        lines += ["", "Odometer readings: none recorded."]
    if subs:
        lines += ["", "Subcategories as 'name (entries)':", "  " + ", ".join(f"{s} ({c})" for s, c in subs)]
    if send_merchants:
        merchants = q(
            "SELECT merchant, count(*) FROM v_entries WHERE merchant IS NOT NULL "
            f"GROUP BY 1 HAVING count(*) >= {MIN_MERCHANT_USES} ORDER BY 2 DESC LIMIT {MAX_MERCHANTS}"
        )
        if merchants:
            lines += ["", "Frequent merchants as 'name (entries)':", "  " + ", ".join(f"{m} ({c})" for m, c in merchants)]
    lines += ["", *_examples(date_tokens(today), [name for name, _ in subs], bool(odo_n))]
    return "\n".join(lines)


def _examples(t: dict[str, str], tags: list[str], has_odometer: bool) -> list[str]:
    """Worked examples with today's real dates. Small models follow these far better than rules."""
    out = ["Examples (same style, same date literals):"]

    def add(question: str, sql: str) -> None:
        out.extend([f"  Q: {question}", f"  SQL: {sql}"])

    if tags:
        tag = tags[0]
        add(
            f"How much did I spend on {tag} last month?",
            f"SELECT SUM(amount) AS spent FROM v_expenses WHERE subcategory = '{tag}' "
            f"AND txn_date >= '{t['last_month_start']}' AND txn_date <= '{t['last_month_end']}'",
        )
        add(
            f"How many {tag} entries in the last 30 days?",
            f"SELECT COUNT(*) AS n FROM v_expenses WHERE subcategory = '{tag}' "
            f"AND txn_date >= '{t['days_30_ago']}' AND txn_date <= '{t['today']}'",
        )
        add(
            f"How much did I spend on {tag} in the last six months?",
            f"SELECT SUM(amount) AS spent FROM v_expenses WHERE subcategory = '{tag}' "
            f"AND txn_date >= '{t['six_months_ago']}' AND txn_date <= '{t['today']}'",
        )
    add(
        "Spend per month over the last three months",
        "SELECT month, SUM(amount) AS spent FROM v_expenses "
        f"WHERE txn_date >= '{t['three_full_months_start']}' AND txn_date <= '{t['last_month_end']}' "
        "GROUP BY month ORDER BY month",
    )
    add(
        "Average monthly spend over the last three months",
        "SELECT AVG(t) AS avg_monthly_spend FROM (SELECT SUM(amount) AS t FROM v_expenses "
        f"WHERE txn_date >= '{t['three_full_months_start']}' AND txn_date <= '{t['last_month_end']}' GROUP BY month)",
    )
    if has_odometer:
        add(
            "Petrol spend last month and km driven",
            "SELECT (SELECT SUM(amount) FROM v_expenses WHERE merchant LIKE '%petrol%' "
            f"AND txn_date >= '{t['last_month_start']}' AND txn_date <= '{t['last_month_end']}') AS spent, "
            "(SELECT MAX(odometer_km) - MIN(odometer_km) FROM v_expenses WHERE odometer_km IS NOT NULL "
            f"AND txn_date >= '{t['last_month_start']}' AND txn_date <= '{t['last_month_end']}') AS km_driven",
        )
    return out

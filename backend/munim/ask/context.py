"""The text the model gets about your data. Names and counts only: never amounts, never rows."""

from __future__ import annotations

import calendar
import os
import sqlite3
from datetime import date, timedelta

from munim.db.views import ACCOUNT_COLUMNS, BILL_COLUMNS, CARD_COLUMNS, COLUMNS, SNAPSHOT_COLUMNS

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
        "  v_cards, v_bills: credit cards and the bills typed in for them (see below).",
        "  v_accounts, v_snapshots, v_holdings: accounts (bank, broker, funds, PF) and the values typed in for them.",
        "Columns of v_expenses and v_entries, identical in both:",
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
    cards = q("SELECT card, statement_day, archived FROM v_cards ORDER BY card")
    lines += ["", "Credit cards. v_cards columns:", *[f"  {name}: {desc}" for name, desc in CARD_COLUMNS]]
    lines += ["v_bills columns:", *[f"  {name}: {desc}" for name, desc in BILL_COLUMNS]]
    if cards:
        n_bills, b_first, b_last = q("SELECT count(*), min(statement_date), max(statement_date) FROM v_bills")[0]
        lines += [
            "Cards as 'name (bill day, archived)': " + ", ".join(f"{c} (day {d}{', archived' if a else ''})" for c, d, a in cards),
            f"Bills recorded: {n_bills}" + (f", from {b_first} to {b_last}." if n_bills else "."),
        ]
    else:
        lines += ["No cards have been added yet."]
    accounts = q("SELECT account, type, archived FROM v_accounts ORDER BY account")
    lines += [
        "",
        "Accounts. v_accounts columns:", *[f"  {name}: {desc}" for name, desc in ACCOUNT_COLUMNS],
        "v_snapshots columns (v_holdings has the same columns but only the newest row of each live account):",
        *[f"  {name}: {desc}" for name, desc in SNAPSHOT_COLUMNS],
    ]
    if accounts:
        n_snaps, s_first, s_last = q("SELECT count(*), min(as_of), max(as_of) FROM v_snapshots")[0]
        lines += [
            "Accounts as 'name (type, archived)': "
            + ", ".join(f"{a} ({t}{', archived' if x else ''})" for a, t, x in accounts),
            f"Values recorded: {n_snaps}" + (f", from {s_first} to {s_last}." if n_snaps else "."),
        ]
    else:
        lines += ["No accounts have been added yet."]
    if subs:
        lines += ["", "Subcategories as 'name (entries)':", "  " + ", ".join(f"{s} ({c})" for s, c in subs)]
    if send_merchants:
        merchants = q(
            "SELECT merchant, count(*) FROM v_entries WHERE merchant IS NOT NULL "
            f"GROUP BY 1 HAVING count(*) >= {MIN_MERCHANT_USES} ORDER BY 2 DESC LIMIT {MAX_MERCHANTS}"
        )
        if merchants:
            lines += ["", "Frequent merchants as 'name (entries)':", "  " + ", ".join(f"{m} ({c})" for m, c in merchants)]
    lines += ["", *_examples(date_tokens(today), [name for name, _ in subs], bool(odo_n), bool(cards), bool(accounts))]
    return "\n".join(lines)


# Each live account counts its newest value on or before that month: a month with no new entry carries the old one.
_NET_WORTH_HISTORY = (
    "SELECT month, SUM(v) AS net_worth FROM (SELECT m.month AS month, "
    "(SELECT s.value FROM v_snapshots s WHERE s.account = a.account AND s.month <= m.month "
    "ORDER BY s.as_of DESC LIMIT 1) AS v FROM (SELECT DISTINCT month FROM v_snapshots) m, v_accounts a "
    "WHERE a.archived = 0) GROUP BY month ORDER BY month"
)
_LATEST_BILLS = (
    "SELECT card, statement_date, amount, due_date, is_paid FROM v_bills b "
    "WHERE statement_date = (SELECT MAX(statement_date) FROM v_bills WHERE card = b.card) ORDER BY card"
)


def _examples(t: dict[str, str], tags: list[str], has_odometer: bool, has_cards: bool = False, has_accounts: bool = False) -> list[str]:
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
            f"How much did I spend on {tag} in the last twelve months?",
            f"SELECT SUM(amount) AS spent FROM v_expenses WHERE subcategory = '{tag}' "
            f"AND txn_date >= '{t['twelve_months_ago']}' AND txn_date <= '{t['today']}'",
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
    if has_cards:
        add("What is my latest bill on each card?", _LATEST_BILLS)
        add(
            "Which bills are unpaid?",
            "SELECT card, statement_date, amount, due_date FROM v_bills WHERE is_paid = 0 ORDER BY due_date",
        )
        add(
            "Which bills are overdue?",
            f"SELECT card, amount, due_date FROM v_bills WHERE is_paid = 0 AND due_date < '{t['today']}' ORDER BY due_date",
        )
        add(
            "How much did my cards bill me per month this year?",
            f"SELECT month, card, SUM(amount) AS billed FROM v_bills WHERE statement_date >= '{t['year_start']}' "
            "GROUP BY month, card ORDER BY month",
        )
    if has_accounts:
        add("What is my net worth?", "SELECT SUM(value) AS net_worth, MAX(as_of) AS latest_entry FROM v_holdings")
        add("Net worth by account type", "SELECT type, SUM(value) AS total FROM v_holdings GROUP BY type ORDER BY total DESC")
        add("What is my total gain on investments?", "SELECT SUM(gain) AS gain, SUM(invested) AS invested FROM v_holdings WHERE invested IS NOT NULL")
        add(
            "How has my Dhan account grown?",
            "SELECT as_of, value FROM v_snapshots WHERE LOWER(account) LIKE '%dhan%' ORDER BY as_of",
        )
        add("Net worth month by month", _NET_WORTH_HISTORY)
    return out

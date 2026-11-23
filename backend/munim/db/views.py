"""The only tables the question layer can see.

v_expenses  money you actually spent (kind = 'expense', live rows only)
v_entries   every live entry: expenses, income and transfers (SIPs, EMIs)
v_cards     credit cards you track by hand (name, bill day, days to pay)
v_bills     the statements you typed in for those cards
v_accounts  bank, broker, fund and PF accounts you track by hand
v_snapshots every value you typed in for those accounts, by date
v_holdings  the latest value of each live account: net worth is the sum of this

The card views are separate on purpose: card bills are typed totals, not purchases, and they
are never part of v_expenses, so a bill can not be added to spend by mistake.

Spend questions default to v_expenses *structurally*, so a 40,000 SIP can never leak into
"how much did I spend" because the model forgot a WHERE clause.
"""

from __future__ import annotations

# (column, meaning). One list drives both the DDL and the schema text sent to the model.
COLUMNS: list[tuple[str, str]] = [
    ("txn_ts", "entry timestamp, 'YYYY-MM-DD HH:MM:SS.fff'"),
    ("txn_date", "date only, 'YYYY-MM-DD'"),
    ("month", "'YYYY-MM'"),
    ("kind", "'expense' | 'income' | 'transfer'"),
    ("amount", "INR, always positive"),
    ("category", "clean category name, e.g. 'Food'"),
    ("subcategory", "lowercase tag from the note prefix, e.g. 'coffee', 'eatout', 'delivery'; often NULL"),
    ("merchant", "lowercase note text without the prefix, e.g. 'blue tokai'; NULL when there was no note"),
    ("note", "the note exactly as typed"),
    ("description", "free text, e.g. fuel type; often NULL. Never parse numbers out of it"),
    ("odometer_km", "the car's odometer reading typed on some car entries (fuel, service); cumulative; usually NULL"),
]

VIEW_NAMES = ("v_expenses", "v_entries", "v_cards", "v_bills", "v_accounts", "v_snapshots", "v_holdings")

# (v_bills looks the card name up with a subquery rather than a JOIN, and both card views carry a filter SQLite cannot optimise away (it would drop `id IS NOT NULL`).
# Without that, SQLite reports the bare table under a plain count(*) outside the view, which the
# read-only connection has to refuse.)
# Which real tables each view may read. Anything else a query reaches for is refused.
VIEW_SOURCES: dict[str, set[str]] = {
    "v_expenses": {"transactions"},
    "v_entries": {"transactions"},
    "v_cards": {"cards"},
    "v_bills": {"cards", "bills"},
    "v_accounts": {"accounts"},
    "v_snapshots": {"accounts", "snapshots"},
    "v_holdings": {"accounts", "snapshots"},
}

CARD_COLUMNS: list[tuple[str, str]] = [
    ("card", "card name, e.g. 'HSBC Live+'"),
    ("statement_day", "day of the month the bill is generated, 1 to 31"),
    ("due_days", "days allowed to pay after the bill is generated; NULL when not set"),
    ("archived", "1 when the card is archived, else 0"),
]
ACCOUNT_COLUMNS: list[tuple[str, str]] = [
    ("account", "account name, e.g. 'Dhan'"),
    ("type", "'cash' | 'equity' | 'mutual_fund' | 'debt' | 'other'"),
    ("archived", "1 when archived (left out of net worth), else 0"),
]
SNAPSHOT_COLUMNS: list[tuple[str, str]] = [
    ("account", "account name"),
    ("type", "the account's type"),
    ("as_of", "date the value was typed in, 'YYYY-MM-DD'"),
    ("month", "'YYYY-MM' of as_of"),
    ("value", "what the account was worth that day, INR"),
    ("invested", "amount put in so far, INR; NULL when not given"),
    ("gain", "value minus invested; NULL when invested is NULL"),
]
BILL_COLUMNS: list[tuple[str, str]] = [
    ("card", "card name, same as v_cards.card"),
    ("statement_date", "date the bill was generated, 'YYYY-MM-DD'"),
    ("month", "'YYYY-MM' of the statement date"),
    ("amount", "total due on that bill, INR"),
    ("min_due", "minimum due, INR; often NULL"),
    ("due_date", "'YYYY-MM-DD' or NULL"),
    ("paid_on", "date it was paid, or NULL when unpaid"),
    ("is_paid", "1 when paid, else 0"),
]

_SELECT = """SELECT txn_ts,
       date(txn_ts) AS txn_date,
       strftime('%Y-%m', txn_ts) AS month,
       kind, amount, category, subcategory, merchant,
       note_raw AS note, description, odometer_km
FROM transactions
WHERE deleted_at IS NULL"""

VIEW_DDL = {
    "v_expenses": f"CREATE VIEW v_expenses AS\n{_SELECT}\n  AND kind = 'expense'",
    "v_entries": f"CREATE VIEW v_entries AS\n{_SELECT}",
    "v_cards": """CREATE VIEW v_cards AS
SELECT name AS card, statement_day, due_days,
       CASE WHEN archived_at IS NULL THEN 0 ELSE 1 END AS archived
FROM cards
WHERE name > ''""",
    "v_accounts": """CREATE VIEW v_accounts AS
SELECT name AS account, type,
       CASE WHEN archived_at IS NULL THEN 0 ELSE 1 END AS archived
FROM accounts
WHERE name > ''""",
    "v_snapshots": """CREATE VIEW v_snapshots AS
SELECT (SELECT name FROM accounts WHERE id = s.account_id) AS account,
       (SELECT type FROM accounts WHERE id = s.account_id) AS type,
       s.as_of, strftime('%Y-%m', s.as_of) AS month, s.value, s.invested,
       CASE WHEN s.invested IS NULL THEN NULL ELSE s.value - s.invested END AS gain
FROM snapshots s
WHERE s.as_of > ''""",
    "v_holdings": """CREATE VIEW v_holdings AS
SELECT (SELECT name FROM accounts WHERE id = s.account_id) AS account,
       (SELECT type FROM accounts WHERE id = s.account_id) AS type,
       s.as_of, strftime('%Y-%m', s.as_of) AS month, s.value, s.invested,
       CASE WHEN s.invested IS NULL THEN NULL ELSE s.value - s.invested END AS gain
FROM snapshots s
WHERE s.account_id IN (SELECT id FROM accounts WHERE archived_at IS NULL)
  AND s.as_of = (SELECT MAX(as_of) FROM snapshots WHERE account_id = s.account_id)""",
    "v_bills": """CREATE VIEW v_bills AS
SELECT (SELECT name FROM cards WHERE id = b.card_id) AS card,
       b.statement_date,
       strftime('%Y-%m', b.statement_date) AS month,
       b.amount, b.min_due, b.due_date, b.paid_on,
       CASE WHEN b.paid_on IS NULL THEN 0 ELSE 1 END AS is_paid
FROM bills b
WHERE b.statement_date > ''""",
}


def create_views(conn) -> None:
    """Recreate on every start so a changed definition never goes stale."""
    for name, ddl in VIEW_DDL.items():
        conn.exec_driver_sql(f"DROP VIEW IF EXISTS {name}")
        conn.exec_driver_sql(ddl)

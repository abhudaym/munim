"""The only tables the question layer can see.

v_expenses  money you actually spent (kind = 'expense', live rows only)
v_entries   every live entry: expenses, income and transfers (SIPs, EMIs)

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
    ("description", "free text, e.g. fuel type and odometer; often NULL"),
]

VIEW_NAMES = ("v_expenses", "v_entries")

_SELECT = """SELECT txn_ts,
       date(txn_ts) AS txn_date,
       strftime('%Y-%m', txn_ts) AS month,
       kind, amount, category, subcategory, merchant,
       note_raw AS note, description
FROM transactions
WHERE deleted_at IS NULL"""

VIEW_DDL = {
    "v_expenses": f"CREATE VIEW v_expenses AS\n{_SELECT}\n  AND kind = 'expense'",
    "v_entries": f"CREATE VIEW v_entries AS\n{_SELECT}",
}


def create_views(conn) -> None:
    """Recreate on every start so a changed definition never goes stale."""
    for name, ddl in VIEW_DDL.items():
        conn.exec_driver_sql(f"DROP VIEW IF EXISTS {name}")
        conn.exec_driver_sql(ddl)

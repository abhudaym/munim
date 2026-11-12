"""First line of defence: reject anything that is not one plain SELECT over our two views.

This gives the model a readable error to fix. The real boundary is the read-only connection
and SQLite authorizer in runner.py, which still holds if this check is ever wrong.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from munim.db.views import VIEW_NAMES


class GuardError(ValueError):
    """The SQL is not allowed. The message is safe to show and to send back to the model."""


_FORBIDDEN = tuple(
    cls
    for name in (
        "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Pragma",
        "Attach", "Detach", "Transaction", "Commit", "Rollback", "Set", "Merge",
    )
    if (cls := getattr(exp, name, None)) is not None
)


def check_sql(sql: str) -> str:
    """Return the SQL to run (trailing semicolon removed) or raise GuardError."""
    cleaned = (sql or "").strip().rstrip(";").strip()
    if not cleaned:
        raise GuardError("The query is empty.")

    try:
        statements = [s for s in sqlglot.parse(cleaned, read="sqlite") if s is not None]
    except SqlglotError as exc:
        raise GuardError(f"The SQL could not be parsed: {exc}") from exc
    if len(statements) != 1:
        raise GuardError("Exactly one statement is allowed.")

    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise GuardError("Only SELECT queries are allowed.")
    if tree.find(*_FORBIDDEN):
        raise GuardError("Only SELECT queries are allowed.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise GuardError("Table functions are not allowed.")
        if table.args.get("db") or table.args.get("catalog"):
            raise GuardError("Schema-qualified tables are not allowed.")
        name = table.name.lower()
        if name in cte_names:
            continue
        if name not in VIEW_NAMES:
            raise GuardError(f"Unknown table '{table.name}'. Query only {' or '.join(VIEW_NAMES)}.")
    return cleaned

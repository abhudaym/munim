"""Run model-written SQL as safely as SQLite allows.

Four layers, any one of which stops a write:
  1. the file is opened read-only (mode=ro) and PRAGMA query_only is on
  2. an authorizer denies everything except SELECT, function calls, and reads of the two views
     (the base table is readable only when one of those views is doing the reading)
  3. a progress handler aborts the query after a few seconds
  4. at most MAX_ROWS rows come back
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from munim.db.views import VIEW_NAMES

MAX_ROWS = 500
TIMEOUT_S = 5.0
_BLOCKED_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


class QueryError(RuntimeError):
    """The query failed to run. The message is safe to send back to the model."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool = False


_REAL_OBJECTS: set[str] = set()
_BLOCKED_PREFIXES = ("pragma_", "sqlite_", "dbstat")


def _authorizer(action, arg1, arg2, _db, source):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if (arg2 or "").lower() in _BLOCKED_FUNCTIONS else sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        table = (arg1 or "").lower()
        if table in VIEW_NAMES:
            return sqlite3.SQLITE_OK
        # The views read the base table on our behalf; direct reads of it are refused.
        if table == "transactions" and (source or "").lower() in VIEW_NAMES:
            return sqlite3.SQLITE_OK
        # SQLite also reports reads of CTE names (recursive ones, notably). A name that is
        # not a real table, view or internal object can only be a CTE, which is harmless.
        if table not in _REAL_OBJECTS and not table.startswith(_BLOCKED_PREFIXES):
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.execute("PRAGMA query_only=ON")
    _REAL_OBJECTS.update(r[0].lower() for r in conn.execute("SELECT name FROM sqlite_master"))
    _REAL_OBJECTS.add("sqlite_master")
    conn.set_authorizer(_authorizer)  # after the pragma, which it would otherwise deny
    return conn


def _plain(value):
    return value.hex() if isinstance(value, (bytes, bytearray)) else value


def run_query(
    conn: sqlite3.Connection, sql: str, *, max_rows: int = MAX_ROWS, timeout: float = TIMEOUT_S
) -> QueryResult:
    deadline = time.monotonic() + timeout
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchmany(max_rows + 1)
    except sqlite3.DatabaseError as exc:
        text = str(exc)
        if "interrupted" in text:
            raise QueryError(f"The query ran longer than {timeout:g}s and was stopped.") from exc
        if "not authorized" in text:
            raise QueryError("The query touches something that is not allowed. Use only v_expenses or v_entries.") from exc
        raise QueryError(text) from exc
    finally:
        conn.set_progress_handler(None, 0)

    return QueryResult(
        columns=columns,
        rows=[[_plain(v) for v in row] for row in fetched[:max_rows]],
        truncated=len(fetched) > max_rows,
    )

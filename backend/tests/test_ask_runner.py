"""These bypass the guard on purpose: the runner must hold on its own."""

import sqlite3

import pytest

from munim.ask.runner import QueryError, connect_readonly, run_query


@pytest.fixture()
def conn(db_path):
    c = connect_readonly(db_path)
    yield c
    c.close()


def test_select_over_a_view(conn):
    r = run_query(conn, "SELECT sum(amount) AS spent FROM v_expenses")
    assert r.columns == ["spent"] and r.rows == [[4890.0]] and r.truncated is False


def test_cte_over_a_view(conn):
    r = run_query(conn, "WITH x AS (SELECT * FROM v_expenses) SELECT count(*) AS n FROM x")
    assert r.rows == [[8]]


def test_deleted_and_non_expense_rows_are_invisible(conn):
    assert run_query(conn, "SELECT count(*) FROM v_entries").rows == [[10]]  # 11 minus 1 deleted
    kinds = run_query(conn, "SELECT DISTINCT kind FROM v_expenses").rows
    assert kinds == [["expense"]]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM transactions",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM imports",
        "SELECT * FROM questions",
        "SELECT * FROM pragma_table_info('transactions')",
        "WITH t AS (SELECT * FROM transactions) SELECT * FROM t",
        "PRAGMA query_only = OFF",
        "ATTACH DATABASE ':memory:' AS x",
        "SELECT load_extension('nope')",
    ],
)
def test_forbidden_reads_are_refused(conn, sql):
    with pytest.raises(QueryError):
        run_query(conn, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM transactions",
        "UPDATE transactions SET amount = 0",
        "INSERT INTO imports (filename, sha256) VALUES ('x', 'y')",
        "DROP TABLE transactions",
        "DROP VIEW v_expenses",
        "CREATE TABLE evil (x)",
    ],
)
def test_writes_are_refused_and_nothing_changes(conn, db_path, sql):
    with pytest.raises(QueryError):
        run_query(conn, sql)
    check = sqlite3.connect(db_path)
    assert check.execute("SELECT count(*), sum(amount) FROM transactions").fetchone() == (11, 244990.0)
    check.close()


def test_row_cap(conn):
    r = run_query(conn, "SELECT * FROM v_entries", max_rows=3)
    assert len(r.rows) == 3 and r.truncated is True


def test_runaway_query_is_stopped(conn):
    forever = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c"
    with pytest.raises(QueryError, match="longer than"):
        run_query(conn, forever, timeout=0.3)


def test_connection_is_reusable_after_a_failure(conn):
    with pytest.raises(QueryError):
        run_query(conn, "SELECT nope FROM v_expenses")
    assert run_query(conn, "SELECT count(*) FROM v_expenses").rows == [[8]]

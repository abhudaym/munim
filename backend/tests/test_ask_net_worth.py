"""Ask can answer net worth questions from the hand-entered account values, and only through the views."""

import sqlite3
from datetime import date

import pytest

from munim.ask import Draft, ask
from munim.ask.context import _NET_WORTH_HISTORY, build_context
from munim.ask.guard import GuardError, check_sql
from munim.ask.runner import QueryError, connect_readonly, run_query
from munim.db.session import make_session_factory
from tests.helpers import FakeLLM

TODAY = date(2026, 11, 23)


@pytest.fixture()
def worth_db(db_path):
    conn = sqlite3.connect(db_path)
    accounts = [(1, "Dhan", "equity", None), (2, "HDFC savings", "cash", None), (3, "Old PF", "debt", "2026-10-01")]
    conn.executemany("INSERT INTO accounts (id, name, type, archived_at, created_at) VALUES (?,?,?,?,'2026-01-01')", accounts)
    snaps = [
        (1, "2026-08-02", 100000.0, 90000.0),
        (1, "2026-10-10", 130000.0, 95000.0),
        (2, "2026-09-05", 40000.0, None),
        (2, "2026-10-12", 55000.0, None),
        (3, "2026-08-01", 500000.0, None),  # archived: left out of net worth
    ]
    conn.executemany("INSERT INTO snapshots (account_id, as_of, value, invested) VALUES (?,?,?,?)", snaps)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def conn(worth_db):
    c = connect_readonly(worth_db)
    yield c
    c.close()


def test_holdings_is_the_latest_value_of_each_live_account(conn):
    r = run_query(conn, "SELECT account, value, gain FROM v_holdings ORDER BY account")
    assert r.rows == [["Dhan", 130000.0, 35000.0], ["HDFC savings", 55000.0, None]]
    assert run_query(conn, "SELECT SUM(value) FROM v_holdings").rows == [[185000.0]]


def test_snapshots_keep_every_entry_including_archived_accounts(conn):
    assert run_query(conn, "SELECT count(*) FROM v_snapshots").rows == [[5]]
    assert run_query(conn, "SELECT account, type FROM v_accounts WHERE archived = 1").rows == [["Old PF", "debt"]]


def test_net_worth_by_month_carries_values_forward(conn):
    r = run_query(conn, _NET_WORTH_HISTORY)
    assert r.rows == [["2026-08", 100000.0], ["2026-09", 140000.0], ["2026-10", 185000.0]]


@pytest.mark.parametrize("sql", ["SELECT * FROM accounts", "SELECT * FROM snapshots", "SELECT count(*) FROM snapshots"])
def test_account_tables_stay_closed(conn, sql):
    with pytest.raises(QueryError):
        run_query(conn, sql)
    with pytest.raises(GuardError):
        check_sql(sql)


@pytest.mark.parametrize("view", ["v_accounts", "v_snapshots", "v_holdings"])
def test_counting_over_each_view_works(conn, view):
    assert run_query(conn, f"SELECT count(*) FROM {view}").rows[0][0] > 0


def test_context_lists_accounts_and_examples(worth_db):
    ctx = build_context(connect_readonly(worth_db), TODAY, send_merchants=False)
    assert "v_holdings" in ctx and "Dhan (equity)" in ctx and "Old PF (debt, archived)" in ctx
    assert "Values recorded: 5, from 2026-08-01 to 2026-10-12." in ctx and "What is my net worth?" in ctx
    assert "130000" not in ctx and "185000" not in ctx  # names and counts only, never amounts


def test_context_without_accounts_says_so(db_path):
    ctx = build_context(connect_readonly(db_path), TODAY, send_merchants=False)
    assert "No accounts have been added yet." in ctx and "What is my net worth?" not in ctx


def test_ask_answers_net_worth(worth_db, session):
    llm = FakeLLM(Draft(sql="SELECT SUM(value) AS net_worth, MAX(as_of) AS latest_entry FROM v_holdings", note="Latest value of each live account."))
    result = ask(
        "what is my net worth?", db_path=worth_db, llm=llm,
        session_factory=make_session_factory(session.get_bind()), today=TODAY,
    )
    assert result.error is None and result.rows == [[185000.0, "2026-10-12"]]


def test_net_worth_by_month_draws_a_line(worth_db, session):
    llm = FakeLLM(Draft(sql=_NET_WORTH_HISTORY, note="Net worth at each month with an entry."))
    result = ask(
        "net worth month by month", db_path=worth_db, llm=llm,
        session_factory=make_session_factory(session.get_bind()), today=TODAY,
    )
    assert result.error is None and result.chart in ("line", "bars") and result.time is True

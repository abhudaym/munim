"""Ask can answer questions about the hand-entered card bills, and only those."""

import sqlite3
from datetime import date

import pytest

from munim.ask import Draft, ask
from munim.ask.context import build_context
from munim.ask.guard import GuardError, check_sql
from munim.ask.runner import QueryError, connect_readonly, run_query
from munim.db.session import make_session_factory
from tests.helpers import FakeLLM

TODAY = date(2026, 11, 23)


@pytest.fixture()
def cards_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO cards (name, statement_day, due_days, color, image, created_at) VALUES ('HSBC Live+', 20, 18, '#112233', 'secret.png', '2026-01-01')")
    conn.execute("INSERT INTO cards (name, statement_day, due_days, created_at) VALUES ('Axis Amex', 5, 15, '2026-01-01')")
    bills = [
        (1, "2026-09-20", 18750.0, "2026-10-08", "2026-10-06"),
        (1, "2026-10-20", 27480.0, "2026-11-07", None),  # overdue
        (2, "2026-10-05", 51200.0, "2026-10-20", "2026-10-19"),
        (2, "2026-11-05", 33650.0, "2026-11-20", None),  # overdue as of the 23rd
    ]
    conn.executemany("INSERT INTO bills (card_id, statement_date, amount, due_date, paid_on) VALUES (?,?,?,?,?)", bills)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def conn(cards_db):
    c = connect_readonly(cards_db)
    yield c
    c.close()


def test_views_expose_cards_and_bills(conn):
    assert run_query(conn, "SELECT card, statement_day FROM v_cards ORDER BY card").rows == [["Axis Amex", 5], ["HSBC Live+", 20]]
    r = run_query(conn, "SELECT card, month, amount, is_paid FROM v_bills WHERE statement_date = '2026-10-20'")
    assert r.rows == [["HSBC Live+", "2026-10", 27480.0, 0]]


def test_picture_and_colour_never_reach_the_model(conn):
    cols = run_query(conn, "SELECT * FROM v_cards").columns
    assert cols == ["card", "statement_day", "due_days", "archived"]
    assert "image" not in run_query(conn, "SELECT * FROM v_bills").columns


@pytest.mark.parametrize("sql", ["SELECT * FROM cards", "SELECT * FROM bills", "SELECT image FROM cards"])
def test_the_card_tables_themselves_stay_closed(conn, sql):
    with pytest.raises(QueryError):
        run_query(conn, sql)
    with pytest.raises(GuardError):
        check_sql(sql)


def test_a_card_view_cannot_be_used_to_reach_transactions(conn):
    with pytest.raises(QueryError):
        run_query(conn, "SELECT * FROM v_bills, transactions")


def test_bills_are_not_spending(conn):
    assert run_query(conn, "SELECT sum(amount) FROM v_expenses").rows == [[4890.0]]


def test_context_lists_cards_and_examples(cards_db):
    ctx = build_context(connect_readonly(cards_db), TODAY, send_merchants=False)
    assert "v_bills" in ctx and "HSBC Live+ (day 20)" in ctx and "Bills recorded: 4, from 2026-09-20 to 2026-11-05." in ctx
    assert "Which bills are overdue?" in ctx and "'2026-11-23'" in ctx
    assert "secret.png" not in ctx and "#112233" not in ctx


def test_context_without_cards_says_so(db_path):
    ctx = build_context(connect_readonly(db_path), TODAY, send_merchants=False)
    assert "No cards have been added yet." in ctx and "Which bills are overdue?" not in ctx


def test_ask_answers_a_bill_question(cards_db, session):
    sql = "SELECT card, amount FROM v_bills WHERE is_paid = 0 AND due_date < '2026-11-23' ORDER BY due_date"
    llm = FakeLLM(Draft(sql=sql, note="Unpaid bills past their due date as of 2026-11-23."))
    result = ask(
        "which bills are overdue?", db_path=cards_db, llm=llm,
        session_factory=make_session_factory(session.get_bind()), today=TODAY,
    )
    assert result.error is None
    assert result.rows == [["HSBC Live+", 27480.0], ["Axis Amex", 33650.0]]


def test_bills_over_time_by_card_draw_as_a_line(cards_db, session):
    sql = "SELECT month, card, SUM(amount) AS billed FROM v_bills GROUP BY month, card ORDER BY month"
    llm = FakeLLM(Draft(sql=sql, note="Bill totals by statement month."))
    result = ask(
        "bills per month per card", db_path=cards_db, llm=llm,
        session_factory=make_session_factory(session.get_bind()), today=TODAY,
    )
    assert result.chart == "line" and result.plot and {s["name"] for s in result.plot["series"]} == {"HSBC Live+", "Axis Amex"}


def test_counting_over_the_views_works_but_not_over_the_tables(conn):
    assert run_query(conn, "SELECT count(*) FROM v_bills").rows == [[4]]
    assert run_query(conn, "SELECT count(*), min(statement_date) FROM v_bills").rows == [[4, "2026-09-20"]]
    with pytest.raises(QueryError):
        run_query(conn, "SELECT count(*) FROM bills")
    with pytest.raises(QueryError):
        run_query(conn, "SELECT count(*) FROM cards")

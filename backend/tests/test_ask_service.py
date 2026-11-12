from datetime import date

import pytest
from sqlalchemy import select

from munim.ask import AskResult, Draft, LLMError, ask
from munim.ask.context import build_context, date_tokens
from munim.ask.runner import connect_readonly
from munim.db import Question
from munim.db.session import make_session_factory
from tests.helpers import FakeLLM

TODAY = date(2026, 4, 10)
COFFEE_TOTAL = "SELECT sum(amount) AS spent FROM v_expenses WHERE subcategory = 'coffee'"


@pytest.fixture()
def factory(session):
    return make_session_factory(session.get_bind())


def run(db_path, factory, llm, question="how much on coffee?", **kw):
    return ask(question, db_path=db_path, llm=llm, session_factory=factory, today=TODAY, **kw)


def test_answer_with_a_headline_number(db_path, factory):
    llm = FakeLLM(Draft(COFFEE_TOTAL, "Coffee spend, all dates."))
    out = run(db_path, factory, llm)
    assert out.error is None and out.attempts == 1
    assert out.headline == 1440 and out.rows == [[1440.0]] and out.columns == ["spent"]
    assert out.note == "Coffee spend, all dates." and out.model == "fake-model"


def test_table_answer_has_no_headline(db_path, factory):
    sql = "SELECT month, sum(amount) AS spent FROM v_expenses GROUP BY month ORDER BY month"
    out = run(db_path, factory, FakeLLM(Draft(sql, None)))
    assert out.headline is None
    assert out.rows == [["2026-02", 550.0], ["2026-03", 4050.0], ["2026-04", 290.0]]


def test_spend_excludes_transfers_income_and_deleted_rows(db_path, factory):
    out = run(db_path, factory, FakeLLM(Draft("SELECT sum(amount) FROM v_expenses", None)))
    assert out.headline == 4890  # no 40,000 SIP, no 1,98,000 salary, no deleted petrol


def test_everything_view_includes_income(db_path, factory):
    sql = "SELECT sum(amount) FROM v_entries WHERE kind = 'income'"
    assert run(db_path, factory, FakeLLM(Draft(sql, None))).headline == 198000


def test_retry_after_a_guard_error(db_path, factory):
    llm = FakeLLM(Draft("SELECT sum(amount) FROM transactions", "first try"), Draft(COFFEE_TOTAL, "fixed"))
    out = run(db_path, factory, llm)
    assert out.attempts == 2 and out.error is None and out.headline == 1440
    sent_sql, sent_error = llm.calls[1]["previous"]
    assert "transactions" in sent_sql and "Unknown table" in sent_error
    assert llm.calls[0]["previous"] is None


def test_retry_after_a_sqlite_error(db_path, factory):
    llm = FakeLLM(Draft("SELECT sum(nope) FROM v_expenses", None), Draft(COFFEE_TOTAL, None))
    out = run(db_path, factory, llm)
    assert out.attempts == 2 and out.headline == 1440
    assert "nope" in llm.calls[1]["previous"][1]


def test_gives_up_after_two_failures(db_path, factory):
    llm = FakeLLM(Draft("DROP TABLE transactions", None), Draft("SELECT * FROM transactions", None))
    out = run(db_path, factory, llm)
    assert out.attempts == 2 and out.error and out.rows == [] and out.headline is None
    assert out.sql == "SELECT * FROM transactions"  # kept, so it can be shown


def test_model_can_decline(db_path, factory):
    out = run(db_path, factory, FakeLLM(Draft(None, "I only know your spending, not balances.")))
    assert out.sql is None and out.error is None and out.rows == []
    assert "balances" in out.note


def test_model_failure_is_raised_and_logged(db_path, factory, session):
    with pytest.raises(LLMError):
        run(db_path, factory, FakeLLM(LLMError("boom")))
    logged = session.scalars(select(Question)).all()
    assert [q.error for q in logged] == ["boom"]


def test_every_question_is_logged_without_rows(db_path, factory, session):
    run(db_path, factory, FakeLLM(Draft(COFFEE_TOTAL, "ok")), question="  how much   on   coffee? ")
    (q,) = session.scalars(select(Question)).all()
    assert q.question == "how much on coffee?" and q.sql == COFFEE_TOTAL
    assert q.row_count == 1 and q.error is None and q.attempts == 1 and q.model == "fake-model"


def test_log_can_be_switched_off(db_path, factory, session):
    run(db_path, factory, FakeLLM(Draft(COFFEE_TOTAL, None)), log=False)
    assert session.scalars(select(Question)).all() == []


def test_truncated_flag_is_passed_through(db_path, factory, monkeypatch):
    monkeypatch.setattr("munim.ask.service.run_query", lambda c, s: __import__("munim.ask.runner", fromlist=["x"]).run_query(c, s, max_rows=2))
    out = run(db_path, factory, FakeLLM(Draft("SELECT * FROM v_entries", None)))
    assert out.truncated is True and len(out.rows) == 2


# ---------------------------------------------------------------- what the model is told

def context(db_path, **kw):
    conn = connect_readonly(db_path)
    try:
        return build_context(conn, TODAY, **kw)
    finally:
        conn.close()


def test_context_has_names_and_dates_but_no_amounts(db_path):
    text = context(db_path)
    assert "Today is Friday 2026-04-10" in text
    assert "2026-02-19 to 2026-04-02 (10 entries)" in text  # the deleted entry is not counted
    assert "Food (expense" in text and "Investments (transfer" in text and "Salary (income" in text
    assert "coffee (5)" in text and "eatout (2)" in text
    for amount in ("198000", "40000", "2100", "1200"):
        assert amount not in text
    assert "month_start = 2026-04-01" in text and "three_months_ago = 2026-01-10" in text


def test_context_lists_only_repeated_merchants(db_path):
    text = context(db_path)
    assert "blue tokai (4)" in text
    assert "mcd" not in text and "paul's" not in text  # used once each


def test_merchants_can_be_withheld(db_path):
    assert "Frequent merchants" not in context(db_path, send_merchants=False)


def test_merchants_env_switch(db_path, monkeypatch):
    monkeypatch.setenv("MUNIM_SEND_MERCHANTS", "0")
    assert "Frequent merchants" not in context(db_path)


def test_date_tokens_handle_month_ends_and_january():
    t = date_tokens(date(2026, 3, 31))
    assert t["last_month_start"] == "2026-02-01" and t["last_month_end"] == "2026-02-28"
    assert t["three_months_ago"] == "2025-12-31" and t["six_months_ago"] == "2025-09-30"
    jan = date_tokens(date(2026, 1, 15))
    assert jan["last_month_start"] == "2025-12-01" and jan["last_month_end"] == "2025-12-31"
    assert jan["year_start"] == "2026-01-01" and jan["twelve_months_ago"] == "2025-01-15"


def test_result_is_a_plain_dict(db_path, factory):
    out = run(db_path, factory, FakeLLM(Draft(COFFEE_TOTAL, None)))
    assert isinstance(out, AskResult) and out.to_dict()["headline"] == 1440

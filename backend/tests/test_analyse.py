import json
from datetime import date

import pytest

from munim.analyse import AnalyseConfigError, Goal, LocalChat, analyse, fact_pack, inr, unmatched_numbers
from munim.analyse.facts import Fact
from munim.ask import Draft
from munim.ask.llm import LLMError
from munim.ask.runner import connect_readonly
from munim.db.session import make_session_factory
from tests.helpers import FakeLLM

TODAY = date(2026, 4, 10)  # ask_rows(): Feb and Mar are whole months, April is running


class FakeChat:
    name = "fake-14b"
    local = True

    def __init__(self, *replies, reachable=True, has_model=True):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self._status = {"reachable": reachable, "has_model": has_model}

    def chat(self, system, user, *, as_json=False, max_tokens=700):
        self.calls.append({"system": system, "user": user, "as_json": as_json})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def status(self):
        return self._status


@pytest.fixture()
def facts(db_path):
    conn = connect_readonly(db_path)
    try:
        return {f.key: f for f in fact_pack(conn, TODAY)}
    finally:
        conn.close()


def test_inr_uses_indian_grouping():
    assert [inr(v) for v in (999, 1234, 123456, 12345678.4, -5000)] == ["₹999", "₹1,234", "₹1,23,456", "₹1,23,45,678", "-₹5,000"]


def test_fact_pack_averages_whole_months_only(facts):
    # Feb: 550 spent. Mar: 198000 in, 4050 spent, 40000 invested. April is unfinished and left out.
    assert facts["period"].text == "Feb 2026 to Mar 2026 (2 whole months)"
    assert facts["avg_income"].value == 99000
    assert facts["avg_spent"].value == 2300
    assert facts["avg_invested"].value == 20000
    assert facts["avg_emi"].value == 0
    assert facts["avg_left"].value == 76700
    assert facts["spend_share"].text == "2.3%"
    assert facts["save_rate"].text == "97.7%"
    assert facts["high_month"].text == "Mar 2026, ₹4,050" and facts["low_month"].text == "Feb 2026, ₹550"
    assert facts["month_so_far"].text == "₹290"
    assert facts["top_categories"].text.startswith("Food ₹1,300 a month (56.5% of spending)")
    assert "net_worth" not in facts and "unpaid_bills" not in facts  # none recorded


def test_goal_facts(db_path):
    conn = connect_readonly(db_path)
    facts = {f.key: f for f in fact_pack(conn, TODAY, Goal(300000, 10, "a trip"))}
    conn.close()
    assert facts["goal_per_month"].text == "₹30,000"
    assert facts["goal_spare"].text == "₹46,700"  # 76,700 left over minus 30,000 needed
    assert facts["goal_months_now"].text == "3.9 months"


def test_empty_database(data_dir, session):
    conn = connect_readonly(data_dir / "munim.db")
    facts = fact_pack(conn, TODAY)
    conn.close()
    assert [f.key for f in facts] == ["empty"]


FACTS = [
    Fact("a", "Average monthly spending", 102637, "inr", "₹1,02,637"),
    Fact("b", "Spending as a share of income", 48.1, "pct", "48.1%"),
    Fact("c", "Highest month", 128386, "inr", "Aug 2026, ₹1,28,386"),
]


@pytest.mark.parametrize(
    "text",
    [
        "You spend ₹1,02,637 a month, 48.1% of your income.",
        "Spending is about ₹1.03L a month.",  # rounded with a unit
        "Your top 3 categories; August 2026 was the peak at ₹1,28,386.",  # small counts and years
        "On 12 Nov you paid it.",  # a day next to a month
    ],
)
def test_checker_accepts_numbers_from_the_facts(text):
    assert unmatched_numbers(text, FACTS) == []


def test_checker_flags_invented_numbers():
    text = "You spend ₹1,02,637, so you could save ₹25,000 more, about 60% of the rest."
    assert unmatched_numbers(text, FACTS) == ["25,000", "60"]


def test_checker_allows_numbers_from_the_question():
    assert unmatched_numbers("A ₹3,00,000 trip is within reach.", FACTS, "trip for 300000") == []


def _run(db_path, session, chat, ask_llm=None, **kw):
    return analyse(
        "Is my spending too much for my income?", db_path=db_path, chat=chat, ask_llm=ask_llm,
        session_factory=make_session_factory(session.get_bind()), today=TODAY, **kw,
    )


def test_answer_from_facts_passes_first_time(db_path, session):
    chat = FakeChat('{"extra": []}', "No. You spend 2.3% of your income.\n- Average monthly spending is ₹2,300.")
    result = _run(db_path, session, chat, ask_llm=FakeLLM())
    assert result.flagged is False and result.attempts == 1 and result.queries == []
    assert "₹2,300" in result.answer
    assert chat.calls[0]["as_json"] is True and "Average monthly spending" in chat.calls[0]["user"]
    assert "₹2,300" not in chat.calls[0]["user"]  # the planner sees labels, not amounts
    assert "Average monthly spending: ₹2,300" in chat.calls[1]["user"]


def test_invented_number_gets_one_retry(db_path, session):
    chat = FakeChat('{"extra": []}', "You could save ₹50,000 more.", "You spend ₹2,300 a month.")
    result = _run(db_path, session, chat, ask_llm=FakeLLM())
    assert result.attempts == 2 and result.flagged is False
    assert "50,000" in chat.calls[2]["user"]


def test_still_wrong_after_retry_is_flagged(db_path, session):
    chat = FakeChat('{"extra": []}', "Save ₹50,000.", "Save ₹45,000.")
    result = _run(db_path, session, chat, ask_llm=FakeLLM())
    assert result.flagged is True and result.unmatched == ["45,000"]


def test_extra_fact_comes_from_ask(db_path, session):
    ask_llm = FakeLLM(Draft(sql="SELECT SUM(amount) AS spent FROM v_expenses WHERE subcategory = 'coffee'", note="Coffee, all time."))
    chat = FakeChat(json.dumps({"extra": ["How much have I spent on coffee?"]}), "Coffee came to ₹1,440.")
    result = _run(db_path, session, chat, ask_llm=ask_llm)
    assert result.queries[0]["rows"] == [[1440.0]] and result.queries[0]["error"] is None
    assert result.flagged is False
    assert "How much have I spent on coffee?: ₹1,440" in chat.calls[1]["user"]


def test_extra_query_failure_does_not_stop_the_answer(db_path, session):
    ask_llm = FakeLLM(Draft(sql="DELETE FROM transactions", note=None), Draft(sql="DROP TABLE x", note=None))
    chat = FakeChat('{"extra": ["delete everything"]}', "You spend ₹2,300 a month.")
    result = _run(db_path, session, chat, ask_llm=ask_llm)
    assert result.queries[0]["error"] and result.answer.startswith("You spend")


def test_bad_plan_is_ignored(db_path, session):
    chat = FakeChat("not json at all", "You spend ₹2,300 a month.")
    result = _run(db_path, session, chat, ask_llm=FakeLLM())
    assert result.queries == [] and result.flagged is False


def test_without_ask_there_is_no_planning(db_path, session):
    chat = FakeChat("You spend ₹2,300 a month.")
    result = _run(db_path, session, chat, ask_llm=None)
    assert len(chat.calls) == 1 and result.flagged is False


def test_only_local_servers_are_allowed():
    with pytest.raises(AnalyseConfigError):
        LocalChat("https://api.groq.com/openai/v1")
    assert LocalChat("http://127.0.0.1:11434/v1").local is True


def test_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from munim.api.app import create_app

    chat = FakeChat("Nothing is recorded yet.")
    app = create_app(tmp_path / "d", load_llm_from_env=False, analyst=chat)
    with TestClient(app) as c:
        status = c.get("/api/analyse/status").json()
        assert status == {"ready": True, "model": "fake-14b", "reachable": True, "has_model": True, "problem": None}
        r = c.post("/api/analyse", json={"question": "am I saving enough?"})
        assert r.status_code == 200, r.text
        assert r.json()["answer"] == "Nothing is recorded yet." and r.json()["facts"][0]["key"] == "empty"
        assert c.post("/api/analyse", json={"question": "x"}).status_code == 422
        assert c.post("/api/analyse", json={"question": "save for a car", "goal_amount": 500000}).status_code == 422


def test_api_reports_a_model_failure(tmp_path):
    from fastapi.testclient import TestClient

    from munim.api.app import create_app

    app = create_app(tmp_path / "d", load_llm_from_env=False, analyst=FakeChat(LLMError("Could not reach Ollama")))
    with TestClient(app) as c:
        r = c.post("/api/analyse", json={"question": "am I saving enough?"})
        assert r.status_code == 502 and "Ollama" in r.json()["detail"]


def test_api_refuses_a_remote_analyse_server(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from munim.api.app import create_app

    monkeypatch.setenv("MUNIM_ANALYSE_BASE_URL", "https://example.com/v1")
    with TestClient(create_app(tmp_path / "d", load_llm_from_env=True)) as c:
        status = c.get("/api/analyse/status").json()
        assert status["ready"] is False and "not local" in status["problem"]
        assert c.post("/api/analyse", json={"question": "am I saving enough?"}).status_code == 503

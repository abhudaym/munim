import pytest
from fastapi.testclient import TestClient

from munim.api.app import create_app
from munim.ask import Draft, LLMError
from tests.helpers import FakeLLM

COFFEE = "SELECT sum(amount) AS spent FROM v_expenses WHERE subcategory = 'coffee'"


@pytest.fixture()
def make_client(db_path, data_dir):
    clients = []

    def build(llm):
        c = TestClient(create_app(data_dir, llm=llm, load_llm_from_env=False))
        c.__enter__()
        clients.append(c)
        return c

    yield build
    for c in clients:
        c.__exit__(None, None, None)


def test_status_without_a_model(make_client):
    body = make_client(None).get("/api/ask/status").json()
    assert body["ready"] is False and body["model"] is None


def test_status_with_a_model(make_client):
    body = make_client(FakeLLM()).get("/api/ask/status").json()
    assert body == {"ready": True, "model": "fake-model", "local": False, "sends_merchants": True}


def test_ask_without_a_model_is_503(make_client):
    r = make_client(None).post("/api/ask", json={"question": "coffee spend?"})
    assert r.status_code == 503 and "MUNIM_PROVIDER" in r.json()["detail"]


def test_ask_answers_and_history_records_it(make_client):
    c = make_client(FakeLLM(Draft(COFFEE, "Coffee, all time.")))
    r = c.post("/api/ask", json={"question": "how much on coffee?"})
    assert r.status_code == 200
    body = r.json()
    assert body["headline"] == 1440 and body["sql"] == COFFEE and body["note"] == "Coffee, all time."
    (h,) = c.get("/api/ask/history").json()
    assert h["question"] == "how much on coffee?" and h["row_count"] == 1 and h["error"] is None


def test_unanswerable_query_is_reported_not_raised(make_client):
    c = make_client(FakeLLM(Draft("SELECT * FROM transactions", None), Draft("DROP TABLE x", None)))
    body = c.post("/api/ask", json={"question": "show everything"}).json()
    assert body["error"] and body["rows"] == []


def test_model_outage_is_502(make_client):
    r = make_client(FakeLLM(LLMError("overloaded"))).post("/api/ask", json={"question": "coffee spend?"})
    assert r.status_code == 502 and "overloaded" in r.json()["detail"]


@pytest.mark.parametrize("question", ["", "hi", "x" * 501])
def test_question_length_is_validated(make_client, question):
    assert make_client(FakeLLM()).post("/api/ask", json={"question": question}).status_code == 422

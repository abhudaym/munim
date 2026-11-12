import io
import json
import urllib.error

import pytest

from munim.ask import AnthropicSQLWriter, LLMError, OpenAICompatSQLWriter, writer_from_env
from munim.ask.llm import JSON_SYSTEM, parse_draft

SQL = "SELECT sum(amount) AS spent FROM v_expenses"


class Reply:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *a):
        return False


def content(text):
    return {"choices": [{"message": {"content": text}}]}


@pytest.mark.parametrize(
    "text,sql,note",
    [
        (json.dumps({"sql": SQL, "note": "All time."}), SQL, "All time."),
        ("```json\n" + json.dumps({"sql": SQL, "note": "x"}) + "\n```", SQL, "x"),
        ("Here you go: " + json.dumps({"sql": SQL, "note": ""}) + " Hope it helps", SQL, None),
        (json.dumps({"sql": "", "note": "No balances here."}), None, "No balances here."),
        ("```sql\n" + SQL + "\n```", SQL, None),
        (SQL, SQL, None),
    ],
)
def test_parse_draft_forgives_small_model_habits(text, sql, note):
    draft = parse_draft(text)
    assert draft.sql == sql and draft.note == note


@pytest.mark.parametrize("text", ["", "I cannot help with that.", "{}"])
def test_parse_draft_rejects_non_answers(text):
    with pytest.raises(LLMError):
        parse_draft(text)


def test_request_shape_and_answer():
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data)
        return Reply(content(json.dumps({"sql": SQL, "note": "ok"})))

    w = OpenAICompatSQLWriter("https://api.groq.com/openai/v1/", "some-model", api_key="k", opener=opener)
    draft = w.write_query("coffee?", "CONTEXT", previous=("SELECT x", "no such column: x"))
    assert draft.sql == SQL and w.local is False
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions" and seen["auth"] == "Bearer k"
    body = seen["body"]
    assert body["model"] == "some-model" and body["temperature"] == 0
    assert body["messages"][0]["content"] == JSON_SYSTEM
    user = body["messages"][1]["content"]
    assert "CONTEXT" in user and "coffee?" in user and "no such column: x" in user


def test_local_server_needs_no_key_and_is_marked_local():
    def opener(request, timeout):
        assert request.get_header("Authorization") is None
        return Reply(content(SQL))

    w = OpenAICompatSQLWriter("http://localhost:11434/v1", "qwen2.5-coder:7b", opener=opener)
    assert w.local is True and w.write_query("q", "c").sql == SQL


def test_unreachable_local_server_says_how_to_start_it():
    def opener(request, timeout):
        raise urllib.error.URLError("Connection refused")

    w = OpenAICompatSQLWriter("http://localhost:11434/v1", "m", opener=opener)
    with pytest.raises(LLMError, match="ollama serve"):
        w.write_query("q", "c")


def test_http_error_and_bad_payload_become_llm_errors():
    def rate_limited(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {}, io.BytesIO(b"slow down"))

    with pytest.raises(LLMError, match="429"):
        OpenAICompatSQLWriter("https://x.test/v1", "m", opener=rate_limited).write_query("q", "c")
    with pytest.raises(LLMError, match="unexpected"):
        OpenAICompatSQLWriter("https://x.test/v1", "m", opener=lambda r, timeout: Reply({"nope": 1})).write_query("q", "c")


def test_provider_selection(monkeypatch):
    for var in ("MUNIM_PROVIDER", "MUNIM_BASE_URL", "GROQ_API_KEY", "MUNIM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert writer_from_env() is None  # nothing set

    monkeypatch.setenv("MUNIM_PROVIDER", "ollama")
    w = writer_from_env()
    assert isinstance(w, OpenAICompatSQLWriter) and w.name == "qwen2.5-coder:7b" and w.local

    monkeypatch.setenv("MUNIM_MODEL", "qwen2.5-coder:14b")
    assert writer_from_env().name == "qwen2.5-coder:14b"

    monkeypatch.setenv("MUNIM_PROVIDER", "groq")
    assert writer_from_env() is None  # no key
    monkeypatch.setenv("GROQ_API_KEY", "k")
    w = writer_from_env()
    assert w.base_url == "https://api.groq.com/openai/v1" and not w.local
    monkeypatch.delenv("MUNIM_MODEL")
    assert writer_from_env() is None  # groq needs an explicit model

    monkeypatch.setenv("MUNIM_PROVIDER", "nonsense")
    assert writer_from_env() is None

    monkeypatch.setenv("MUNIM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert isinstance(writer_from_env(), AnthropicSQLWriter)

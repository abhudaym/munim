"""The model that writes SQL. Behind a small interface so tests (and evals) can swap it."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"

_INTRO = "You turn one question about a person's finances into one read-only SQLite query. "
_RULES = """

Rules:
- Use v_expenses for anything about spending. Use v_entries only for income, investments, transfers \
or "everything", and then filter kind explicitly.
- Dates are text 'YYYY-MM-DD'. Filter with txn_date >= 'a' AND txn_date <= 'b', copying the \
ready-made dates from the context. "this month" = month_start..today. "last month" = \
last_month_start..last_month_end. "this year" = year_start..today. "last 3/6/12 months" = \
three_months_ago / six_months_ago / twelve_months_ago .. today. "last 30 days" = days_30_ago..today. \
Never use date('now') or arithmetic on today. For a named month use that month's literal first and last \
day, in the latest year that has data for it.
- category must match a listed name exactly. subcategory and merchant are lowercase; match merchant with \
LIKE '%text%' in lowercase. Words like coffee, eating out and delivery are subcategories (coffee, eatout, \
delivery) when they are listed.
- A single total or count over "the last 3/6/12 months" runs from three_months_ago / six_months_ago / \
twelve_months_ago to today, including the current month so far. But when the question says "per month", \
"monthly", "each month", "month by month" or "average per month" it wants calendar months, so a partial first \
month must never appear: use whole calendar months: \
txn_date >= three_full_months_start / six_full_months_start / twelve_full_months_start AND txn_date <= \
last_month_end. Then say in note that the current, unfinished month is left out.
- "Average per month" is AVG over a subquery that first sums by month: SELECT AVG(t) FROM (SELECT SUM(amount) \
AS t FROM ... GROUP BY month). AVG(amount) alone is the average entry, which is a different thing.
- "Biggest/largest single expense" means one entry: ORDER BY amount DESC LIMIT 1 with its date, category, \
note and amount. Never SUM for it.
- When a subcategory or merchant already answers the question (coffee, petrol), filter on that alone. Do not \
add a category filter as well; the same tag can sit under more than one category.
- Never select a non-aggregated column next to SUM/COUNT/AVG without a GROUP BY on it.
- Totals use SUM(amount). Name money columns spent, total or amount, and counts n.
- Return only what was asked: one number for "how much" or "how many"; a short ranked list (10 rows unless \
told otherwise) for "top" or "biggest"; a month column, ordered by month, for per-month breakdowns.
- Distance driven: odometer_km is a cumulative reading, so never SUM it. Distance over a period is \
MAX(odometer_km) - MIN(odometer_km) across every row in that period where odometer_km IS NOT NULL, whatever \
its category or merchant (a service entry can carry a reading too), so compute it in its own subquery \
when the question also filters on fuel; name it km_driven. Distance per fill-up is odometer_km minus the previous reading (LAG ... OVER (ORDER BY txn_ts)). \
If the readings start later or end earlier than the period asked for, say in note which dates the distance \
really covers. Cost per km divides only the spend between the first and last reading by that distance.
- A question with two parts (a total and a distance) is still one query: return them as two columns.
- One statement. No comments. SQLite syntax only.
- If the question cannot be answered from these views (balances, net worth, market value of investments, \
dates outside the data), set sql to an empty string and explain in note.
- note: one short sentence saying what the query measures and the exact date range, so the person can spot \
a misreading."""

SYSTEM = _INTRO + "Always answer by calling the write_query tool." + _RULES
JSON_SYSTEM = (
    _INTRO
    + 'Answer with one JSON object and nothing else: {"sql": "<query or empty string>", "note": "<one sentence>"}.'
    + _RULES
)

TOOL = {
    "name": "write_query",
    "description": "Return the SQL that answers the question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "The SELECT query, or an empty string if it cannot be answered."},
            "note": {"type": "string", "description": "One short sentence: what it measures and the date range used."},
        },
        "required": ["sql", "note"],
    },
}


class LLMError(RuntimeError):
    """The model call failed. Nothing to retry on our side."""


@dataclass
class Draft:
    sql: str | None  # None: the model says it cannot answer
    note: str | None


class SQLWriter(Protocol):
    name: str

    def write_query(self, question: str, context: str, previous: tuple[str, str] | None = None) -> Draft: ...


class AnthropicSQLWriter:
    local = False

    def __init__(self, client=None, model: str | None = None):
        import anthropic

        self._anthropic = anthropic
        self.client = client or anthropic.Anthropic(timeout=30.0)
        self.name = model or os.environ.get("MUNIM_MODEL") or DEFAULT_MODEL

    @classmethod
    def from_env(cls) -> AnthropicSQLWriter | None:
        return cls() if os.environ.get("ANTHROPIC_API_KEY") else None

    def write_query(self, question: str, context: str, previous: tuple[str, str] | None = None) -> Draft:
        prompt = _prompt(question, context, previous)
        try:
            response = self.client.messages.create(
                model=self.name,
                max_tokens=1024,
                system=SYSTEM,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": TOOL["name"]},
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as exc:
            raise LLMError(f"The model call failed: {type(exc).__name__}: {exc}") from exc

        block = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
        if block is None:
            raise LLMError("The model did not return a query.")
        data = block.input or {}
        sql = (data.get("sql") or "").strip()
        note = (data.get("note") or "").strip() or None
        return Draft(sql=sql or None, note=note)


def _prompt(question: str, context: str, previous: tuple[str, str] | None) -> str:
    prompt = f"{context}\n\nQuestion: {question}"
    if previous:
        sql, error = previous
        prompt += f"\n\nYour previous query failed.\nQuery:\n{sql}\nError: {error}\nWrite a corrected query."
    return prompt


_FENCE = re.compile(r"```(?:sql|json)?\s*(.*?)```", re.S | re.I)


def parse_draft(text: str) -> Draft:
    """Read {"sql", "note"} from a model reply, forgiving the ways small models stray from it."""
    text = (text or "").strip()
    candidates = [text] + _FENCE.findall(text)
    brace = re.search(r"\{.*\}", text, re.S)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and "sql" in data:
            sql = str(data.get("sql") or "").strip()
            note = str(data.get("note") or "").strip() or None
            return Draft(sql=sql or None, note=note)
    for candidate in _FENCE.findall(text) + [text]:  # bare SQL, fenced or not
        if re.match(r"\s*(select|with)\b", candidate, re.I):
            return Draft(sql=candidate.strip(), note=None)
    raise LLMError("The model did not return a query.")


PROVIDERS = {
    # name: (base URL, env var holding the key, default model)
    "ollama": ("http://localhost:11434/v1", None, "qwen2.5-coder:7b"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", None),
    "openai-compatible": (None, "MUNIM_API_KEY", None),
}
_LOCAL_HOSTS = ("://localhost", "://127.0.0.1", "://[::1]")


class OpenAICompatSQLWriter:
    """Any server that speaks /chat/completions: Ollama on this machine, Groq, and others."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 120.0, opener=None):
        self.base_url = base_url.rstrip("/")
        self.name = model
        self.api_key = api_key
        self.timeout = timeout  # generous: a local model may need to load first
        self.local = self.base_url.startswith(tuple("http" + h for h in _LOCAL_HOSTS))
        self._open = opener or urllib.request.urlopen

    def write_query(self, question: str, context: str, previous: tuple[str, str] | None = None) -> Draft:
        body = {
            "model": self.name,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": JSON_SYSTEM},
                {"role": "user", "content": _prompt(question, context, previous)},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            with self._open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise LLMError(f"{self.name} answered HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            hint = " Is Ollama running? Start it with `ollama serve`." if self.local else ""
            raise LLMError(f"Could not reach {self.base_url}: {getattr(exc, 'reason', exc)}.{hint}") from exc
        except ValueError as exc:
            raise LLMError("The model server sent a reply that is not JSON.") from exc
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("The model server sent an unexpected reply.") from exc
        return parse_draft(text)


def writer_from_env() -> SQLWriter | None:
    """Pick the model from MUNIM_PROVIDER. None means Ask is not set up."""
    provider = (os.environ.get("MUNIM_PROVIDER") or "anthropic").strip().lower()
    if provider == "anthropic":
        return AnthropicSQLWriter.from_env()
    if provider not in PROVIDERS:
        return None
    base, key_var, default_model = PROVIDERS[provider]
    base = os.environ.get("MUNIM_BASE_URL") or base
    model = os.environ.get("MUNIM_MODEL") or default_model
    key = os.environ.get(key_var) if key_var else None
    if not base or not model or (provider == "groq" and not key):
        return None
    return OpenAICompatSQLWriter(base, model, api_key=key)

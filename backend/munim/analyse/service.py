"""Plan, gather, write, check. The flow behind the Analyse mode."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from munim.analyse.checker import unmatched_numbers
from munim.analyse.facts import Fact, Goal, fact_pack, inr
from munim.analyse.llm import LocalChat
from munim.ask.llm import LLMError, SQLWriter
from munim.ask.runner import connect_readonly
from munim.ask.service import ask

MAX_EXTRA = 2
MAX_TABLE_ROWS = 12

PLAN_SYSTEM = """You plan a short money analysis for one person. You are given their question and the \
facts already computed. Decide whether one or two extra facts would really help answer it, for example \
spending on one category or tag, or one card's bills. Each extra fact must be a plain question about their \
own recorded expenses, income, card bills or account values, answerable by one database query. Do not ask \
for anything the facts already cover, and do not ask about prices, the market or the future. \
Answer with JSON only: {"extra": ["question", ...]} with at most two questions, or {"extra": []}."""

WRITE_SYSTEM = """You are a careful money analyst writing to one person in India about their own finances. \
Answer their question in plain, direct English using only the facts given.

Rules:
- Every number you write must be copied exactly as it appears in the facts, with the same ₹, commas and %. \
Do not calculate, add, subtract, divide, round or estimate anything. If you want a number that is not in \
the facts, describe it in words instead.
- Start with a one-line answer. Then two to four short points, each starting with "- ", each backed by a \
fact. End with one practical suggestion when it fits.
- Under 170 words. No headings, no tables, no bold.
- If the facts cannot answer the question, say exactly what is missing.
- Do not recommend specific funds, stocks or products. Rules of thumb are yardsticks, not targets.
- Say "you", not "the user"."""


@dataclass
class ExtraQuery:
    question: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    note: str | None = None
    error: str | None = None


@dataclass
class AnalyseResult:
    question: str
    answer: str = ""
    facts: list[dict] = field(default_factory=list)
    queries: list[dict] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    flagged: bool = False
    attempts: int = 0
    model: str = ""
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _plan(chat: LocalChat, question: str, facts: list[Fact]) -> list[str]:
    user = "Facts already computed:\n" + "\n".join(f"- {f.label}" for f in facts) + f"\n\nQuestion: {question}"
    try:
        text = chat.chat(PLAN_SYSTEM, user, as_json=True, max_tokens=200)
    except LLMError:
        return []  # planning is a nice-to-have: the fact pack alone still gives an answer
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        return []
    extra = data.get("extra") if isinstance(data, dict) else None
    if not isinstance(extra, list):
        return []
    return [" ".join(str(q).split()) for q in extra if str(q).strip()][:MAX_EXTRA]


def _extra_fact(i: int, q: ExtraQuery) -> Fact | None:
    if q.error or not q.rows:
        return None
    if len(q.rows) == 1 and len(q.columns) == 1:
        value = q.rows[0][0]
        if isinstance(value, (int, float)):
            money = re.search(r"spent|total|amount|billed|value|net_worth|gain|invested", q.columns[0], re.I)
            text = inr(value) if money else f"{value:g}"
            return Fact(f"extra_{i}", q.question, round(value) if money else value, "inr" if money else "count", text)
        return None
    lines, numbers = [], []
    for row in q.rows[:MAX_TABLE_ROWS]:
        cells = []
        for col, cell in zip(q.columns, row):
            if isinstance(cell, float) and re.search(r"spent|total|amount|billed|value|gain|invested", col, re.I):
                cells.append(inr(cell))
                numbers.append(float(round(cell)))
            else:
                cells.append(str(cell))
                if isinstance(cell, (int, float)):
                    numbers.append(float(cell))
        lines.append(", ".join(cells))
    more = f" (first {MAX_TABLE_ROWS} of {len(q.rows)} rows)" if len(q.rows) > MAX_TABLE_ROWS else ""
    return Fact(f"extra_{i}", f"{q.question} [{', '.join(q.columns)}]{more}", unit="table",
                text="; ".join(lines), numbers=numbers)


def _write_prompt(question: str, goal: Goal | None, facts: list[Fact], today: date) -> str:
    lines = [f"Today is {today.isoformat()}.", "", "Facts:", *[f"- {f.line()}" for f in facts], ""]
    if goal:
        lines.append(f"They want to afford {goal.label or 'something'} costing {inr(goal.amount)} in {goal.months} months.")
    lines.append(f"Question: {question}")
    return "\n".join(lines)


def analyse(
    question: str,
    *,
    db_path: str | Path,
    chat: LocalChat,
    ask_llm: SQLWriter | None = None,
    session_factory: sessionmaker[Session] | None = None,
    goal: Goal | None = None,
    today: date | None = None,
) -> AnalyseResult:
    started = time.monotonic()
    today = today or date.today()
    out = AnalyseResult(question=" ".join(question.split()), model=chat.name)

    conn = connect_readonly(db_path)
    try:
        facts = fact_pack(conn, today, goal)
    finally:
        conn.close()

    # Extra facts: the local model names them, Ask writes and runs the query through the usual guard.
    if ask_llm is not None:
        for i, extra_q in enumerate(_plan(chat, out.question, facts), start=1):
            q = ExtraQuery(question=extra_q)
            try:
                res = ask(extra_q, db_path=db_path, llm=ask_llm, session_factory=session_factory, today=today, log=False)
                q.sql, q.columns, q.rows, q.note, q.error = res.sql, res.columns, res.rows, res.note, res.error
                if res.sql is None and not res.error:
                    q.error = res.note or "Ask could not answer this from your data."
            except LLMError as exc:
                q.error = str(exc)
            out.queries.append(asdict(q))
            fact = _extra_fact(i, q)
            if fact:
                facts.append(fact)

    extra_text = out.question + (f" {goal.amount} {goal.months} {goal.label or ''}" if goal else "")
    prompt = _write_prompt(out.question, goal, facts, today)
    answer = chat.chat(WRITE_SYSTEM, prompt)
    out.attempts = 1
    bad = unmatched_numbers(answer, facts, extra_text)
    if bad:
        retry = (
            prompt + "\n\nYour previous answer:\n" + answer + "\n\nThese numbers in it are not in the facts: "
            + ", ".join(bad) + ". Rewrite it using only numbers copied exactly from the facts."
        )
        answer = chat.chat(WRITE_SYSTEM, retry)
        out.attempts = 2
        bad = unmatched_numbers(answer, facts, extra_text)

    out.answer = answer.strip()
    out.unmatched = bad
    out.flagged = bool(bad)
    out.facts = [{"key": f.key, "label": f.label, "text": f.text} for f in facts]
    out.seconds = round(time.monotonic() - started, 1)
    return out

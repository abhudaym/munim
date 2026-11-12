"""Golden-question check: does the model's query return what a hand-written one does?

Needs a real model and data, so it is run by hand (`munim eval`), never in the test suite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from importlib import resources
from itertools import permutations
from pathlib import Path

from munim.ask.context import date_tokens
from munim.ask.runner import connect_readonly, run_query
from munim.ask.service import ask
from munim.ask.llm import SQLWriter


@dataclass
class EvalRow:
    question: str
    ok: bool
    detail: str


def load_golden() -> list[dict]:
    return json.loads(resources.files("munim.ask").joinpath("golden.json").read_text())


def _norm(value):
    return round(value, 2) if isinstance(value, float) else value


def _rows_key(rows: list[list]) -> list[str]:
    return sorted(repr([_norm(v) for v in r]) for r in rows)


def same_answer(got: list[list], want: list[list]) -> bool:
    """Same cells to the paisa, ignoring column names and row order.

    Extra columns are fine: asked "which merchant", an answer of (merchant, total) is right.
    So this passes when some choice of the answer's columns equals the reference.
    """
    if len(got) != len(want):
        return False
    if not want:
        return True
    k, m = len(want[0]), len(got[0])
    if m < k:
        return False
    target = _rows_key(want)
    return any(_rows_key([[r[i] for i in cols] for r in got]) == target for cols in permutations(range(m), k))


def latest_data_date(db_path: Path) -> date:
    conn = connect_readonly(db_path)
    try:
        (latest,) = run_query(conn, "SELECT max(txn_date) FROM v_entries").rows[0]
    finally:
        conn.close()
    return date.fromisoformat(latest) if latest else date.today()


def run_eval(db_path: Path, llm: SQLWriter, today: date | None = None, limit: int | None = None) -> list[EvalRow]:
    today = today or latest_data_date(db_path)
    tokens = date_tokens(today)
    out: list[EvalRow] = []
    conn = connect_readonly(db_path)
    try:
        for item in load_golden()[:limit]:
            got = ask(item["q"], db_path=db_path, llm=llm, today=today, log=False)
            if item["sql"] is None:  # should be declined, not guessed at
                ok = got.sql is None
                out.append(EvalRow(item["q"], ok, "declined" if ok else f"answered anyway: {got.sql}"))
                continue
            want = run_query(conn, item["sql"].format(**tokens)).rows
            if got.error:
                out.append(EvalRow(item["q"], False, f"error: {got.error}"))
            elif same_answer(got.rows, want):
                out.append(EvalRow(item["q"], True, ""))
            else:
                out.append(EvalRow(item["q"], False, f"got {got.rows[:3]} want {want[:3]}\n    {got.sql}"))
    finally:
        conn.close()
    return out

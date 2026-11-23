"""Every number in a written answer must come from the facts. This finds the ones that don't."""

from __future__ import annotations

import re

from munim.analyse.facts import Fact

_MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
_NUMBER = re.compile(
    r"(?<![\w.])(?P<int>\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(?P<dec>\d+))?\s*(?P<mult>lakhs?\b|crores?\b|cr\b|k\b|L\b)?",
    re.I,
)
_MULT = {"k": 1e3, "l": 1e5, "lakh": 1e5, "lakhs": 1e5, "cr": 1e7, "crore": 1e7, "crores": 1e7}
_DATE_NEAR = re.compile(rf"^\s*(?:{_MONTHS})\b|(?:{_MONTHS})\s*$", re.I)


def _allowed(facts: list[Fact], extra_text: str) -> list[float]:
    values: list[float] = []
    for fact in facts:
        if fact.value is not None:
            values.append(float(fact.value))
        values += fact.numbers
        values += [v for v, *_ in _numbers(fact.text)]
    values += [v for v, *_ in _numbers(extra_text)]
    return values


def _numbers(text: str):
    for m in _NUMBER.finditer(text or ""):
        whole = m.group("int").replace(",", "")
        dec = m.group("dec") or ""
        value = float(f"{whole}.{dec}" if dec else whole)
        mult = (m.group("mult") or "").lower()
        scale = _MULT.get(mult, 1.0)
        yield value * scale, len(dec), scale, m


def _ignorable(value: float, decimals: int, scale: float, match: re.Match, text: str) -> bool:
    if scale != 1.0 or decimals:
        return False
    if value <= 10:  # "top 3", "2 categories", "1 card"
        return True
    if 1990 <= value <= 2100 and "," not in match.group("int"):  # a year
        return True
    if value <= 31:  # a day of the month next to a month name: "12 Nov", "Nov 12"
        before, after = text[max(0, match.start() - 10):match.start()], text[match.end():match.end() + 10]
        if _DATE_NEAR.search(before) or _DATE_NEAR.search(after):
            return True
    return False


def unmatched_numbers(answer: str, facts: list[Fact], extra_text: str = "") -> list[str]:
    """Numbers in the answer that no fact, the question or the goal contains, as written."""
    allowed = _allowed(facts, extra_text)
    bad = []
    for value, decimals, scale, match in _numbers(answer):
        if _ignorable(value, decimals, scale, match, answer):
            continue
        # Written with a unit like 1.2L, it may be rounded to the last digit shown.
        rounding = 0.5 * 10 ** -decimals * scale if scale != 1.0 else 0.5 * 10 ** -decimals
        ok = any(abs(value - a) <= max(rounding, 0.6, 0.005 * abs(a)) for a in allowed)
        if not ok:
            bad.append(match.group(0).strip())
    return bad

"""Slow-moving trends over the last 12 full months: savings rate, category growth, when you spend."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from munim.insights.data import Txn, add_months, month_key

MONTHS = 12
HALF = 6
MIN_PRIOR_MONTHS = 3
SLOTS = (("morning", 5, 12), ("afternoon", 12, 17), ("evening", 17, 22), ("late night", 22, 29))
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class SavingsPoint:
    month: str
    income: float
    spent: float  # expenses plus EMIs
    rate: float | None  # (income - spent) / income; None without income


@dataclass
class Growth:
    category: str  # "Income" for the reference row
    recent: float  # monthly average, last HALF months
    before: float  # monthly average, the months before that
    pct: float | None
    faster_than_income: bool


@dataclass
class Trends:
    months: list[str]
    savings: list[SavingsPoint]
    savings_avg: float | None
    growth: list[Growth]
    recent_months: int
    before_months: int
    slots: list[str]
    days: list[str]
    grid: list[list[float]]  # [day][slot] total spend
    weekend_share: float | None
    top_slot: str | None


def _slot(hour: int) -> int:
    h = hour if hour >= 5 else hour + 24
    for i, (_, a, b) in enumerate(SLOTS):
        if a <= h < b:
            return i
    return len(SLOTS) - 1


def trends(txns: list[Txn], today: date) -> Trends:
    this_month = date(today.year, today.month, 1)
    first = min((t.day for t in txns), default=today)
    first_m = date(first.year, first.month, 1)
    months = [add_months(this_month, -i) for i in range(MONTHS, 0, -1)]
    months = [m for m in months if m >= first_m]
    keys = [month_key(m) for m in months]
    inside = set(keys)

    inc: dict[str, float] = defaultdict(float)
    exp: dict[str, float] = defaultdict(float)
    emi: dict[str, float] = defaultdict(float)
    cat: dict[tuple[str, str], float] = defaultdict(float)
    grid = [[0.0] * len(SLOTS) for _ in DAYS]
    for t in txns:
        k = month_key(t.day)
        if k not in inside:
            continue
        if t.kind == "income":
            inc[k] += t.amount
        elif t.kind == "transfer" and t.category.strip().lower() == "emi":
            emi[k] += t.amount  # a loan payment is money gone, not money saved
        elif t.kind == "expense":
            exp[k] += t.amount
            cat[(k, t.category)] += t.amount
            grid[t.ts.weekday()][_slot(t.ts.hour)] += t.amount

    out = {k: exp[k] + emi[k] for k in keys}
    savings = [
        SavingsPoint(k, round(inc[k], 2), round(out[k], 2), round((inc[k] - out[k]) / inc[k], 4) if inc[k] > 0 else None)
        for k in keys
    ]
    tot_inc, tot_exp = sum(inc.values()), sum(out.values())
    savings_avg = round((tot_inc - tot_exp) / tot_inc, 4) if tot_inc > 0 else None

    half = min(HALF, len(keys) // 2)  # with less than a year of entries, compare equal halves
    recent, before = keys[len(keys) - half:], keys[len(keys) - 2 * half:len(keys) - half]
    growth: list[Growth] = []
    if half >= MIN_PRIOR_MONTHS:
        def avg(values: dict, ks: list[str], c: str | None = None) -> float:
            return sum(values[(k, c)] if c else values[k] for k in ks) / len(ks)

        def pct(a: float, b: float) -> float | None:
            return round((a - b) / b, 4) if b > 0 else None

        ir, ib = avg(inc, recent), avg(inc, before)
        income_pct = pct(ir, ib)
        growth.append(Growth("Income", round(ir, 2), round(ib, 2), income_pct, False))
        for c in sorted({c for _, c in cat}):
            r, b = avg(cat, recent, c), avg(cat, before, c)
            if r < 500 and b < 500:  # too small to matter
                continue
            p = pct(r, b)
            faster = p is not None and income_pct is not None and p > income_pct and r - b >= 500
            growth.append(Growth(c, round(r, 2), round(b, 2), p, faster))
        head, rest = growth[:1], growth[1:]
        rest.sort(key=lambda g: (g.pct is None, -(g.pct or 0)))
        growth = head + rest

    total = sum(sum(r) for r in grid)
    weekend = (sum(grid[5]) + sum(grid[6])) / total if total else None
    top = None
    if total:
        d, s = max(((d, s) for d in range(7) for s in range(len(SLOTS))), key=lambda x: grid[x[0]][x[1]])
        top = f"{DAYS[d]} {SLOTS[s][0]}"
    return Trends(
        months=keys, savings=savings, savings_avg=savings_avg, growth=growth,
        recent_months=len(recent) if growth else 0, before_months=len(before) if growth else 0,
        slots=[s[0] for s in SLOTS], days=list(DAYS),
        grid=[[round(v, 2) for v in r] for r in grid],
        weekend_share=None if weekend is None else round(weekend, 4), top_slot=top,
    )

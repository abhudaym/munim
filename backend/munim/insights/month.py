"""This month: pace against your usual, what changed, and entries worth a second look."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from statistics import median

from munim.insights.data import Txn, add_months, month_key, month_len

HISTORY_MONTHS = 6
MIN_MOVE = 1000.0  # a category must move by at least this much to be listed
MAX_MOVERS = 5
BIG_MULTIPLE = 3.0  # "bigger than usual" means this many times the merchant's median
BIG_MIN_EXTRA = 1000.0
NEW_MERCHANT_MIN = 3000.0
DUP_MINUTES = 60
MAX_FLAGS = 10  # the UI shows the first three not dismissed


@dataclass
class Mover:
    category: str
    now: float
    usual: float
    delta: float
    merchants: list[str]


@dataclass
class Flag:
    key: str  # stable id, so the UI can remember a dismissal
    kind: str  # duplicate | big | new
    title: str
    detail: str
    day: date
    amount: float


@dataclass
class MonthInsight:
    month: str
    as_of: date
    day: int
    days_in_month: int
    spent: float
    usual_to_date: float | None  # average spend by this day over the history months
    projected: float | None
    usual_month: float | None  # average full-month spend
    history_months: int
    movers: list[Mover] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)


def _cut(day: int, d: date) -> int:
    return min(day, month_len(d))


def month_insight(txns: list[Txn], today: date) -> MonthInsight:
    start = date(today.year, today.month, 1)
    day = today.day
    expenses = [t for t in txns if t.kind == "expense"]
    now = [t for t in expenses if start <= t.day <= today]
    spent = sum(t.amount for t in now)

    # earlier full months that have any entries, newest first, up to HISTORY_MONTHS
    first = min((t.day for t in txns), default=today)
    hist = []
    for i in range(1, HISTORY_MONTHS + 1):
        m = add_months(start, -i)
        if add_months(m, 1) <= date(first.year, first.month, 1):
            break
        hist.append(m)

    by_month: dict[str, list[Txn]] = defaultdict(list)
    for t in expenses:
        by_month[month_key(t.day)].append(t)

    usual_to_date = projected = usual_month = None
    if hist:
        to_date, rest, full = [], [], []
        for m in hist:
            ts = by_month.get(month_key(m), [])
            cut = _cut(day, m)
            a = sum(t.amount for t in ts if t.day.day <= cut)
            b = sum(t.amount for t in ts if t.day.day > cut)
            to_date.append(a), rest.append(b), full.append(a + b)
        n = len(hist)
        usual_to_date = sum(to_date) / n
        usual_month = sum(full) / n
        projected = spent + sum(rest) / n

    movers: list[Mover] = []
    if hist:
        cur_cat: dict[str, float] = defaultdict(float)
        cur_merch: dict[tuple[str, str], float] = defaultdict(float)
        for t in now:
            cur_cat[t.category] += t.amount
            cur_merch[(t.category, t.merchant)] += t.amount
        old_cat: dict[str, float] = defaultdict(float)
        old_merch: dict[tuple[str, str], float] = defaultdict(float)
        for m in hist:
            cut = _cut(day, m)
            for t in by_month.get(month_key(m), []):
                if t.day.day <= cut:
                    old_cat[t.category] += t.amount / len(hist)
                    old_merch[(t.category, t.merchant)] += t.amount / len(hist)
        for cat in set(cur_cat) | set(old_cat):
            d = cur_cat[cat] - old_cat[cat]
            if abs(d) < MIN_MOVE:
                continue
            keys = {k for k in set(cur_merch) | set(old_merch) if k[0] == cat}
            sign = 1 if d > 0 else -1
            drivers = sorted(keys, key=lambda k: sign * (cur_merch[k] - old_merch[k]), reverse=True)
            names = [k[1] for k in drivers if sign * (cur_merch[k] - old_merch[k]) >= 100 and k[1]][:2]
            movers.append(Mover(cat, round(cur_cat[cat], 2), round(old_cat[cat], 2), round(d, 2), names))
        movers.sort(key=lambda m: abs(m.delta), reverse=True)
        movers = movers[:MAX_MOVERS]

    return MonthInsight(
        month=month_key(start), as_of=today, day=day, days_in_month=month_len(start),
        spent=round(spent, 2),
        usual_to_date=None if usual_to_date is None else round(usual_to_date, 2),
        projected=None if projected is None else round(projected, 2),
        usual_month=None if usual_month is None else round(usual_month, 2),
        history_months=len(hist), movers=movers,
        flags=flags(expenses, start, today),
    )


def _inr(x: float) -> str:
    s = f"{round(x):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return f"₹{s}"


def flags(expenses: list[Txn], start: date, today: date) -> list[Flag]:
    """Same charge twice, much bigger than usual at a merchant, or a large first-time merchant."""
    out: list[Flag] = []
    earlier: dict[str, list[float]] = defaultdict(list)
    for t in expenses:
        if t.day < start and t.merchant:
            earlier[t.merchant].append(t.amount)
    now = [t for t in expenses if start <= t.day <= today]
    # a first-time merchant is only worth a look when the amount is in your top 5% of entries
    past_amounts = sorted(t.amount for t in expenses if t.day < start)
    p95 = past_amounts[int(len(past_amounts) * 0.95)] if len(past_amounts) >= 20 else NEW_MERCHANT_MIN
    new_min = max(NEW_MERCHANT_MIN, p95)

    for a, b in zip(now, now[1:]):
        if a.merchant and a.merchant == b.merchant and a.amount == b.amount and a.day == b.day:
            gap = (b.ts - a.ts).total_seconds() / 60
            if gap <= DUP_MINUTES:
                out.append(Flag(
                    f"dup:{a.merchant}:{a.ts.isoformat()}", "duplicate", "Same charge twice",
                    f"{a.merchant} {_inr(a.amount)} at {a.ts:%H:%M} and {b.ts:%H:%M} on {a.day:%d %b}",
                    a.day, a.amount,
                ))
    for t in now:
        if not t.merchant:
            continue
        past = earlier.get(t.merchant, [])
        if len(past) >= 3:
            usual = median(past)
            if t.amount >= BIG_MULTIPLE * usual and t.amount - usual >= BIG_MIN_EXTRA:
                out.append(Flag(
                    f"big:{t.merchant}:{t.ts.isoformat()}", "big", "Bigger than usual",
                    f"{t.merchant} {_inr(t.amount)} on {t.day:%d %b}. You usually spend about {_inr(usual)} there",
                    t.day, t.amount,
                ))
        elif not past and t.amount >= new_min and sum(1 for x in now if x.merchant == t.merchant) == 1:
            out.append(Flag(
                f"new:{t.merchant}:{t.ts.isoformat()}", "new", "New merchant, large",
                f"{t.merchant} {_inr(t.amount)} on {t.day:%d %b}, first time",
                t.day, t.amount,
            ))
    order = {"duplicate": 0, "big": 1, "new": 2}
    out.sort(key=lambda f: (order[f.kind], -f.amount))
    return out[:MAX_FLAGS]

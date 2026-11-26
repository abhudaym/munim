"""Charges that repeat: same merchant, about the same amount, at a steady gap."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from munim.insights.data import Txn, add_months

MIN_COUNT = 3
AMOUNT_TOLERANCE = 0.15  # within 15% of the median amount
CADENCES = (  # name, typical gap in days, allowed drift in days
    ("weekly", 7, 2),
    ("monthly", 30.4, 6),
    ("quarterly", 91, 12),
    ("yearly", 365, 20),
)
RECENT = 6
STEADY_SHARE = 0.7  # this share of the gaps must sit within the drift


@dataclass
class Recurring:
    merchant: str
    category: str
    kind: str  # expense | transfer
    every: str
    usual: float  # the latest amount
    count: int
    last: date
    next: date | None  # None when it seems to have stopped
    stopped: bool
    previous_amount: float | None  # set when the latest amount differs from the one before


def _collapse(days: list[date], within: float) -> list[date]:
    """Drop a charge that follows the previous one too closely: a late or doubled entry, not a new cycle."""
    out = [days[0]]
    for d in days[1:]:
        if (d - out[-1]).days >= within:
            out.append(d)
    return out


def _cadence(days: list[date]) -> tuple[str, float] | None:
    for name, typical, drift in CADENCES:
        kept = _collapse(days, typical / 3)
        if len(kept) < MIN_COUNT:
            continue
        gaps = [(b - a).days for a, b in zip(kept, kept[1:])]
        g = median(gaps)
        if abs(g - typical) <= drift:
            ok = sum(1 for x in gaps if abs(x - g) <= drift)
            if ok / len(gaps) >= STEADY_SHARE:
                return name, g
    return None


def find_recurring(txns: list[Txn], today: date) -> list[Recurring]:
    groups: dict[tuple[str, str], list[Txn]] = defaultdict(list)
    for t in txns:
        if t.kind in ("expense", "transfer") and t.merchant and t.day <= today:
            groups[(t.kind, t.merchant)].append(t)

    out: list[Recurring] = []
    for (kind, merchant), ts in groups.items():
        ts = sorted(ts, key=lambda t: t.ts)
        # one charge per day at most; a split payment is still one occurrence
        days: dict[date, list[Txn]] = {}
        for t in ts:
            days.setdefault(t.day, []).append(t)
        occ = [(d, sum(t.amount for t in v), v[-1].category) for d, v in sorted(days.items())]
        if len(occ) < MIN_COUNT:
            continue
        latest = occ[-1][1]
        series = occ[-RECENT:]  # judge the amount on recent charges, so an old price does not count against it
        amounts = [a for _, a, _ in series]
        mid = median(amounts)
        if sum(1 for a in amounts if abs(a - mid) <= AMOUNT_TOLERANCE * mid) / len(amounts) < STEADY_SHARE:
            continue
        cad = _cadence([d for d, _, _ in occ])
        if cad is None:
            continue
        name, gap = cad
        last = occ[-1][0]
        expected = _next(last, name, gap)
        _, typical, drift = next(c for c in CADENCES if c[0] == name)
        stopped = (today - last).days > typical + 2 * drift + typical * 0.5
        prev = occ[-2][1]
        changed = abs(prev - latest) > 0.02 * prev
        out.append(Recurring(
            merchant=merchant, category=occ[-1][2], kind=kind, every=name, usual=round(latest, 2),
            count=len(occ), last=last, next=None if stopped else expected, stopped=stopped,
            previous_amount=round(prev, 2) if changed else None,
        ))
    out.sort(key=lambda r: (r.stopped, r.next or date.max))
    return out


def _next(last: date, every: str, gap: float) -> date:
    if every == "monthly":
        # same day next month, clamped; monthly charges keep their date better than a 30-day step
        n = add_months(last, 1)
        nxt = add_months(last, 2)
        return n.replace(day=min(last.day, (nxt - n).days))
    if every == "yearly":
        try:
            return last.replace(year=last.year + 1)
        except ValueError:
            return last.replace(year=last.year + 1, day=28)
    return last + timedelta(days=round(gap))


def still_to_come(items: list[Recurring], today: date) -> list[Recurring]:
    """Recurring charges expected after today and before the month ends."""
    end = add_months(today, 1) - timedelta(days=1)
    return [r for r in items if r.next and today < r.next <= end]

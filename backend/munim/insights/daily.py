"""Day-by-day spend over the last 365 days, for the calendar chart."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from munim.insights.data import Txn

WINDOW_DAYS = 365


@dataclass
class DaySpend:
    day: date
    total: float
    count: int


@dataclass
class Streak:
    days: int
    start: date | None
    end: date | None


@dataclass
class Daily:
    start: date
    end: date
    tracked_from: date | None  # first day with any entry; earlier days are unknown, not "no spend"
    days: list[DaySpend]  # only the days with spend
    total: float
    tracked_days: int
    spend_days: int
    no_spend_days: int
    longest_no_spend: Streak
    current_no_spend: Streak  # the run that ends on the last day; 0 days if you spent that day
    biggest: DaySpend | None


def daily(txns: list[Txn], today: date) -> Daily:
    end = today
    start = end - timedelta(days=WINDOW_DAYS - 1)
    first = min((t.day for t in txns), default=None)
    tracked_from = None if first is None or first > end else max(first, start)

    total: dict[date, float] = defaultdict(float)
    count: dict[date, int] = defaultdict(int)
    for t in txns:
        if t.kind == "expense" and start <= t.day <= end:  # SIPs and EMIs are transfers, not spend
            total[t.day] += t.amount
            count[t.day] += 1
    days = [DaySpend(d, round(total[d], 2), count[d]) for d in sorted(total)]

    longest = Streak(0, None, None)
    current = Streak(0, None, None)
    tracked = 0
    if tracked_from is not None:
        tracked = (end - tracked_from).days + 1
        run_start: date | None = None
        d = tracked_from
        while d <= end:
            if d in total:
                run_start = None
            else:
                run_start = run_start or d
                length = (d - run_start).days + 1
                if length > longest.days:
                    longest = Streak(length, run_start, d)
            d += timedelta(days=1)
        if run_start is not None:  # still running on the last day
            current = Streak((end - run_start).days + 1, run_start, end)

    return Daily(
        start=start, end=end, tracked_from=tracked_from, days=days,
        total=round(sum(total.values()), 2), tracked_days=tracked, spend_days=len(days),
        no_spend_days=tracked - len(days), longest_no_spend=longest, current_no_spend=current,
        biggest=max(days, key=lambda x: x.total, default=None),
    )

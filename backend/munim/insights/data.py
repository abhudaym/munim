from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from munim.db import Transaction


@dataclass(frozen=True)
class Txn:
    ts: datetime
    kind: str  # expense | income | transfer
    amount: float
    category: str
    merchant: str
    odometer_km: int | None = None

    @property
    def day(self) -> date:
        return self.ts.date()


def load(session: Session) -> list[Txn]:
    rows = session.execute(
        select(
            Transaction.txn_ts, Transaction.kind, Transaction.amount, Transaction.category,
            Transaction.merchant, Transaction.odometer_km,
        ).where(Transaction.deleted_at.is_(None)).order_by(Transaction.txn_ts)
    )
    return [Txn(ts, k, float(a), c, (m or "").strip().lower(), o) for ts, k, a, c, m, o in rows]


def as_of(txns: list[Txn], today: date) -> date:
    """The day the numbers are 'as of': today, or the last entry if the data stops earlier."""
    if not txns:
        return today
    return min(today, max(t.day for t in txns))


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months(d: date, n: int) -> date:
    """First day of the month n months from d's month."""
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def month_len(d: date) -> int:
    return (add_months(d, 1) - date(d.year, d.month, 1)).days

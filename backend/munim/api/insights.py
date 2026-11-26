"""Read-only insights computed from the entries. See munim/insights."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from munim.api.deps import get_session
from munim.insights.data import as_of, load
from munim.insights.daily import daily
from munim.insights.garage import garage
from munim.insights.month import month_insight
from munim.insights.recurring import find_recurring, still_to_come
from munim.insights.trends import trends

router = APIRouter(prefix="/api/insights")


def _today(today: date | None) -> date:
    return today or date.today()


@router.get("/month")
def month(today: date | None = Query(None), session: Session = Depends(get_session)):
    """Pace, movers and flags for the month of the latest entry (or today, if entries reach it)."""
    txns = load(session)
    day = as_of(txns, _today(today))
    rec = find_recurring(txns, day)
    upcoming = still_to_come(rec, day)
    out = asdict(month_insight(txns, day))
    out["still_to_come"] = {
        "total": round(sum(r.usual for r in upcoming), 2),
        "items": [asdict(r) for r in upcoming],
    }
    return out


@router.get("/recurring")
def recurring(today: date | None = Query(None), session: Session = Depends(get_session)):
    txns = load(session)
    day = as_of(txns, _today(today))
    items = find_recurring(txns, day)
    live = [r for r in items if not r.stopped]

    def monthly(r) -> float:
        return {"weekly": r.usual * 52 / 12, "monthly": r.usual, "quarterly": r.usual / 3, "yearly": r.usual / 12}[r.every]

    upcoming = still_to_come(items, day)
    return {
        "as_of": day,
        "monthly_total": round(sum(monthly(r) for r in live), 2),
        "still_to_come": round(sum(r.usual for r in upcoming), 2),
        "still_to_come_count": len(upcoming),
        "changed": sum(1 for r in items if r.stopped or r.previous_amount is not None),
        "items": [asdict(r) for r in items],
    }


@router.get("/trends")
def get_trends(today: date | None = Query(None), session: Session = Depends(get_session)):
    txns = load(session)
    day = as_of(txns, _today(today))
    return {"as_of": day, **asdict(trends(txns, day))}


@router.get("/garage")
def get_garage(today: date | None = Query(None), session: Session = Depends(get_session)):
    txns = load(session)
    day = as_of(txns, _today(today))
    return {"as_of": day, **asdict(garage(txns, day))}


@router.get("/daily")
def get_daily(today: date | None = Query(None), session: Session = Depends(get_session)):
    txns = load(session)
    day = as_of(txns, _today(today))
    return {"as_of": day, **asdict(daily(txns, day))}

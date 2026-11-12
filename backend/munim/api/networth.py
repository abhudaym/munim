"""Accounts and what they were worth, entered by hand. Net worth is the latest value of each live account."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from munim.api.deps import get_session
from munim.db import Account, Snapshot, Transaction
from munim.db.models import utcnow

router = APIRouter(prefix="/api")

AccountType = Literal["cash", "equity", "mutual_fund", "debt", "other"]


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: AccountType | None = None
    archived: bool | None = None


class SnapshotIn(BaseModel):
    as_of: date
    value: float = Field(ge=0)
    invested: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=200)


class SnapshotOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    as_of: date
    value: float
    invested: float | None
    note: str | None


class AccountOut(BaseModel):
    id: int
    name: str
    type: str
    archived: bool
    value: float | None  # from the latest snapshot
    invested: float | None
    gain: float | None  # value - invested, when both are known
    as_of: date | None
    days_old: int | None


class TypeRow(BaseModel):
    type: str
    total: float
    share: float  # 0..1 of net worth


class HistoryPoint(BaseModel):
    month: str  # YYYY-MM
    total: float


class Contribution(BaseModel):
    month: str
    total: float


class NetWorth(BaseModel):
    total: float
    as_of: date | None  # the newest snapshot behind the total
    invested: float | None  # sum of invested over accounts that have it
    gain: float | None
    by_type: list[TypeRow]
    history: list[HistoryPoint]
    contributions: list[Contribution]  # "Investments" transfers per month, from Money Manager
    contributed_total: float


def _latest(session: Session) -> dict[int, Snapshot]:
    newest = select(Snapshot.account_id, func.max(Snapshot.as_of).label("d")).group_by(Snapshot.account_id).subquery()
    rows = session.scalars(
        select(Snapshot).join(newest, (Snapshot.account_id == newest.c.account_id) & (Snapshot.as_of == newest.c.d))
    )
    return {s.account_id: s for s in rows}


def _out(account: Account, snap: Snapshot | None, today: date) -> AccountOut:
    gain = None
    if snap and snap.invested is not None:
        gain = round(snap.value - snap.invested, 2)
    return AccountOut(
        id=account.id,
        name=account.name,
        type=account.type,
        archived=account.archived_at is not None,
        value=snap.value if snap else None,
        invested=snap.invested if snap else None,
        gain=gain,
        as_of=snap.as_of if snap else None,
        days_old=(today - snap.as_of).days if snap else None,
    )


def _get(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "No such account")
    return account


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(session: Session = Depends(get_session)):
    latest = _latest(session)
    today = date.today()
    accounts = session.scalars(select(Account).order_by(Account.archived_at.is_not(None), Account.name))
    return [_out(a, latest.get(a.id), today) for a in accounts]


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, session: Session = Depends(get_session)):
    account = Account(name=body.name.strip(), type=body.type)
    session.add(account)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, f"There is already an account called {body.name.strip()!r}") from None
    return _out(account, None, date.today())


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def patch_account(account_id: int, body: AccountPatch, session: Session = Depends(get_session)):
    account = _get(session, account_id)
    if body.name is not None:
        account.name = body.name.strip()
    if body.type is not None:
        account.type = body.type
    if body.archived is not None:
        account.archived_at = utcnow() if body.archived else None
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "There is already an account with that name") from None
    return _out(account, _latest(session).get(account.id), date.today())


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, session: Session = Depends(get_session)):
    account = _get(session, account_id)
    session.query(Snapshot).filter(Snapshot.account_id == account.id).delete()
    session.delete(account)
    session.commit()


@router.get("/accounts/{account_id}/snapshots", response_model=list[SnapshotOut])
def list_snapshots(account_id: int, session: Session = Depends(get_session)):
    _get(session, account_id)
    return session.scalars(select(Snapshot).where(Snapshot.account_id == account_id).order_by(Snapshot.as_of.desc())).all()


@router.post("/accounts/{account_id}/snapshots", response_model=SnapshotOut)
def record_snapshot(account_id: int, body: SnapshotIn, session: Session = Depends(get_session)):
    """Record a value for a day. A second entry for the same day replaces the first."""
    _get(session, account_id)
    if body.as_of > date.today():
        raise HTTPException(422, "The date is in the future")
    snap = session.scalar(select(Snapshot).where(Snapshot.account_id == account_id, Snapshot.as_of == body.as_of))
    if snap is None:
        snap = Snapshot(account_id=account_id, as_of=body.as_of)
        session.add(snap)
    snap.value, snap.invested, snap.note = body.value, body.invested, body.note
    session.commit()
    return snap


@router.delete("/snapshots/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: int, session: Session = Depends(get_session)):
    snap = session.get(Snapshot, snapshot_id)
    if snap is None:
        raise HTTPException(404, "No such snapshot")
    session.delete(snap)
    session.commit()


def _months(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@router.get("/networth", response_model=NetWorth)
def net_worth(session: Session = Depends(get_session)):
    accounts = {a.id: a for a in session.scalars(select(Account).where(Account.archived_at.is_(None)))}
    snaps = list(
        session.scalars(select(Snapshot).where(Snapshot.account_id.in_(accounts)).order_by(Snapshot.as_of))
    ) if accounts else []

    latest: dict[int, Snapshot] = {}
    for s in snaps:  # ordered by date, so the last one seen is the newest
        latest[s.account_id] = s
    total = round(sum(s.value for s in latest.values()), 2)

    by_type: dict[str, float] = {}
    for aid, s in latest.items():
        by_type[accounts[aid].type] = by_type.get(accounts[aid].type, 0) + s.value
    type_rows = [
        TypeRow(type=t, total=round(v, 2), share=(v / total if total else 0))
        for t, v in sorted(by_type.items(), key=lambda kv: -kv[1])
    ]

    with_invested = [s for s in latest.values() if s.invested is not None]
    invested = round(sum(s.invested for s in with_invested), 2) if with_invested else None
    gain = round(sum(s.value - s.invested for s in with_invested), 2) if with_invested else None

    # Month-end history: each account counts its newest entry on or before that month's end.
    history: list[HistoryPoint] = []
    if snaps:
        today_month = date.today().strftime("%Y-%m")
        last_month = max(today_month, snaps[-1].as_of.strftime("%Y-%m"))
        for month in _months(snaps[0].as_of.strftime("%Y-%m"), last_month):
            running: dict[int, float] = {}
            for s in snaps:
                if s.as_of.strftime("%Y-%m") <= month:
                    running[s.account_id] = s.value
            history.append(HistoryPoint(month=month, total=round(sum(running.values()), 2)))

    month_col = func.strftime("%Y-%m", Transaction.txn_ts)
    contrib_rows = session.execute(
        select(month_col, func.sum(Transaction.amount))
        .where(Transaction.deleted_at.is_(None), Transaction.kind == "transfer", Transaction.category == "Investments")
        .group_by(month_col)
        .order_by(month_col)
    ).all()
    contributions = [Contribution(month=m, total=round(t, 2)) for m, t in contrib_rows]

    return NetWorth(
        total=total,
        as_of=snaps[-1].as_of if snaps else None,
        invested=invested,
        gain=gain,
        by_type=type_rows,
        history=history,
        contributions=contributions,
        contributed_total=round(sum(c.total for c in contributions), 2),
    )

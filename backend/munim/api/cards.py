"""Credit cards tracked by hand: when each bill is generated, what it said, and whether it is paid."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from munim.api.deps import get_data_dir, get_session
from munim.db import Bill, Card
from munim.db.models import utcnow

router = APIRouter(prefix="/api")

COLOR = r"^#[0-9a-fA-F]{6}$"
LAST4 = r"^\d{4}$"
MAX_IMAGE = 3 * 1024 * 1024
# Recognised by the first bytes of the file, not by what the upload claims to be.
IMAGE_KINDS = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"RIFF", "webp"))


class CardIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    statement_day: int = Field(ge=1, le=31)
    due_days: int | None = Field(default=None, ge=0, le=60)
    color: str | None = Field(default=None, pattern=COLOR)
    last4: str | None = Field(default=None, pattern=LAST4)


class CardPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    statement_day: int | None = Field(default=None, ge=1, le=31)
    due_days: int | None = Field(default=None, ge=0, le=60)
    color: str | None = Field(default=None, pattern=COLOR)
    last4: str | None = Field(default=None, pattern=LAST4)
    archived: bool | None = None


class BillIn(BaseModel):
    statement_date: date
    amount: float = Field(ge=0)
    min_due: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    paid_on: date | None = None


class BillPatch(BaseModel):
    amount: float | None = Field(default=None, ge=0)
    min_due: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    paid: bool | None = None  # true: paid today (or on paid_on); false: not paid
    paid_on: date | None = None


class BillOut(BaseModel):
    id: int
    statement_date: date
    amount: float
    min_due: float | None
    due_date: date | None
    paid_on: date | None
    status: Literal["paid", "overdue", "due"]
    days_to_due: int | None


class CardOut(BaseModel):
    id: int
    name: str
    statement_day: int
    due_days: int | None
    color: str | None
    last4: str | None
    image_url: str | None
    archived: bool
    next_statement: date
    days_to_statement: int
    last_statement: date  # the most recent statement date; the one to enter a bill for
    suggested_due: date | None  # last_statement + due_days
    last_bill: BillOut | None
    unpaid_total: float
    unpaid_count: int
    next_due: date | None  # earliest due date among unpaid bills
    bills_count: int


def _on(year: int, month: int, day: int) -> date:
    """The given day, or the last day of a shorter month (a 31st statement falls on the 30th or 28th)."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _shift(year: int, month: int, by: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + by
    return index // 12, index % 12 + 1


def statement_dates(day: int, today: date) -> tuple[date, date]:
    """(most recent statement date on or before today, next one after it)."""
    this = _on(today.year, today.month, day)
    if this <= today:
        ny, nm = _shift(today.year, today.month, 1)
        return this, _on(ny, nm, day)
    py, pm = _shift(today.year, today.month, -1)
    return _on(py, pm, day), this


def _bill_out(bill: Bill, today: date) -> BillOut:
    if bill.paid_on:
        status = "paid"
    elif bill.due_date and bill.due_date < today:
        status = "overdue"
    else:
        status = "due"
    return BillOut(
        id=bill.id,
        statement_date=bill.statement_date,
        amount=bill.amount,
        min_due=bill.min_due,
        due_date=bill.due_date,
        paid_on=bill.paid_on,
        status=status,
        days_to_due=(bill.due_date - today).days if bill.due_date and not bill.paid_on else None,
    )


def _card_out(card: Card, bills: list[Bill], today: date) -> CardOut:
    last, nxt = statement_dates(card.statement_day, today)
    ordered = sorted(bills, key=lambda b: b.statement_date, reverse=True)
    unpaid = [b for b in ordered if not b.paid_on]
    dues = [b.due_date for b in unpaid if b.due_date]
    return CardOut(
        id=card.id,
        name=card.name,
        statement_day=card.statement_day,
        due_days=card.due_days,
        color=card.color,
        last4=card.last4,
        image_url=f"/api/cards/{card.id}/image?v={card.image}" if card.image else None,
        archived=card.archived_at is not None,
        next_statement=nxt,
        days_to_statement=(nxt - today).days,
        last_statement=last,
        suggested_due=last + timedelta(days=card.due_days) if card.due_days is not None else None,
        last_bill=_bill_out(ordered[0], today) if ordered else None,
        unpaid_total=round(sum(b.amount for b in unpaid), 2),
        unpaid_count=len(unpaid),
        next_due=min(dues) if dues else None,
        bills_count=len(ordered),
    )


def _card(session: Session, card_id: int) -> Card:
    card = session.get(Card, card_id)
    if card is None:
        raise HTTPException(404, "No such card")
    return card


def _bills(session: Session, card_id: int) -> list[Bill]:
    return list(session.scalars(select(Bill).where(Bill.card_id == card_id)))


@router.get("/cards", response_model=list[CardOut])
def list_cards(session: Session = Depends(get_session)):
    today = date.today()
    by_card: dict[int, list[Bill]] = {}
    for bill in session.scalars(select(Bill)):
        by_card.setdefault(bill.card_id, []).append(bill)
    cards = session.scalars(select(Card).order_by(Card.archived_at.is_not(None), Card.name))
    return [_card_out(c, by_card.get(c.id, []), today) for c in cards]


@router.post("/cards", response_model=CardOut, status_code=201)
def create_card(body: CardIn, session: Session = Depends(get_session)):
    card = Card(
        name=body.name.strip(), statement_day=body.statement_day, due_days=body.due_days,
        color=body.color, last4=body.last4,
    )
    session.add(card)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, f"There is already a card called {body.name.strip()!r}") from None
    return _card_out(card, [], date.today())


@router.patch("/cards/{card_id}", response_model=CardOut)
def patch_card(card_id: int, body: CardPatch, session: Session = Depends(get_session)):
    card = _card(session, card_id)
    changed = body.model_fields_set
    if body.name is not None:
        card.name = body.name.strip()
    if body.statement_day is not None:
        card.statement_day = body.statement_day
    if "due_days" in changed:
        card.due_days = body.due_days
    if "color" in changed:
        card.color = body.color
    if "last4" in changed:
        card.last4 = body.last4
    if body.archived is not None:
        card.archived_at = utcnow() if body.archived else None
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "There is already a card with that name") from None
    return _card_out(card, _bills(session, card.id), date.today())


def _image_dir(data_dir: Path) -> Path:
    path = data_dir / "cards"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _drop_image(card: Card, data_dir: Path) -> None:
    if card.image:
        (_image_dir(data_dir) / card.image).unlink(missing_ok=True)
        card.image = None


@router.put("/cards/{card_id}/image", response_model=CardOut)
async def set_card_image(
    card_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    data_dir: Path = Depends(get_data_dir),
):
    """Your own picture of the card. Kept on this machine under data/cards/."""
    card = _card(session, card_id)
    body = await file.read(MAX_IMAGE + 1)
    if len(body) > MAX_IMAGE:
        raise HTTPException(413, "Image is larger than 3 MB")
    ext = next((e for magic, e in IMAGE_KINDS if body.startswith(magic)), None)
    if ext == "webp" and body[8:12] != b"WEBP":
        ext = None
    if ext is None:
        raise HTTPException(415, "Use a PNG, JPEG or WebP image")
    _drop_image(card, data_dir)
    import hashlib

    card.image = f"{card.id}-{hashlib.sha256(body).hexdigest()[:12]}.{ext}"
    (_image_dir(data_dir) / card.image).write_bytes(body)
    session.commit()
    return _card_out(card, _bills(session, card.id), date.today())


@router.get("/cards/{card_id}/image")
def get_card_image(card_id: int, session: Session = Depends(get_session), data_dir: Path = Depends(get_data_dir)):
    card = _card(session, card_id)
    path = _image_dir(data_dir) / card.image if card.image else None
    if path is None or not path.is_file():
        raise HTTPException(404, "This card has no image")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.delete("/cards/{card_id}/image", response_model=CardOut)
def delete_card_image(card_id: int, session: Session = Depends(get_session), data_dir: Path = Depends(get_data_dir)):
    card = _card(session, card_id)
    _drop_image(card, data_dir)
    session.commit()
    return _card_out(card, _bills(session, card.id), date.today())


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int, session: Session = Depends(get_session), data_dir: Path = Depends(get_data_dir)):
    card = _card(session, card_id)
    _drop_image(card, data_dir)
    session.query(Bill).filter(Bill.card_id == card.id).delete()
    session.delete(card)
    session.commit()


@router.get("/cards/{card_id}/bills", response_model=list[BillOut])
def list_bills(card_id: int, session: Session = Depends(get_session)):
    _card(session, card_id)
    today = date.today()
    bills = sorted(_bills(session, card_id), key=lambda b: b.statement_date, reverse=True)
    return [_bill_out(b, today) for b in bills]


@router.post("/cards/{card_id}/bills", response_model=BillOut)
def record_bill(card_id: int, body: BillIn, session: Session = Depends(get_session)):
    """Record a statement. A second one for the same statement date replaces the first."""
    card = _card(session, card_id)
    if body.statement_date > date.today():
        raise HTTPException(422, "The statement date is in the future")
    due = body.due_date
    if due is None and card.due_days is not None:
        due = body.statement_date + timedelta(days=card.due_days)
    if due is not None and due < body.statement_date:
        raise HTTPException(422, "The due date is before the statement date")
    bill = session.scalar(select(Bill).where(Bill.card_id == card_id, Bill.statement_date == body.statement_date))
    if bill is None:
        bill = Bill(card_id=card_id, statement_date=body.statement_date)
        session.add(bill)
    bill.amount, bill.min_due, bill.due_date, bill.paid_on = body.amount, body.min_due, due, body.paid_on
    session.commit()
    return _bill_out(bill, date.today())


@router.patch("/bills/{bill_id}", response_model=BillOut)
def patch_bill(bill_id: int, body: BillPatch, session: Session = Depends(get_session)):
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(404, "No such bill")
    if body.amount is not None:
        bill.amount = body.amount
    if "min_due" in body.model_fields_set:
        bill.min_due = body.min_due
    if "due_date" in body.model_fields_set:
        bill.due_date = body.due_date
    if body.paid is True:
        bill.paid_on = body.paid_on or date.today()
    elif body.paid is False:
        bill.paid_on = None
    session.commit()
    return _bill_out(bill, date.today())


@router.delete("/bills/{bill_id}", status_code=204)
def delete_bill(bill_id: int, session: Session = Depends(get_session)):
    bill = session.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(404, "No such bill")
    session.delete(bill)
    session.commit()

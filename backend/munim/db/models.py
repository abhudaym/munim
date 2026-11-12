from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

KINDS = ("expense", "income", "transfer")


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC, to match how SQLite stores datetimes."""
    return datetime.now(UTC).replace(tzinfo=None)


class Import(Base):
    """One committed upload. The raw file is archived under data/raw/."""

    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    range_start: Mapped[datetime | None] = mapped_column(DateTime)
    range_end: Mapped[datetime | None] = mapped_column(DateTime)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    rows_in_file: Mapped[int] = mapped_column(Integer, default=0)
    n_new: Mapped[int] = mapped_column(Integer, default=0)
    n_updated: Mapped[int] = mapped_column(Integer, default=0)
    n_deleted: Mapped[int] = mapped_column(Integer, default=0)
    n_unchanged: Mapped[int] = mapped_column(Integer, default=0)


class Question(Base):
    """Every question asked, the SQL it produced, and how it went. Never holds result rows."""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    model: Mapped[str | None] = mapped_column(String(100))


class CategoryMap(Base):
    """Raw category as exported (emoji and all) -> clean name and an optional kind override."""

    __tablename__ = "category_map"

    raw_category: Mapped[str] = mapped_column(String(100), primary_key=True)
    category: Mapped[str] = mapped_column(String(100))
    # None means: follow the row's own direction (income or expense).
    kind: Mapped[str | None] = mapped_column(String(10))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("txn_ts", "dup_seq", name="uq_txn_ts_seq"),
        Index("ix_txn_category", "category"),
        Index("ix_txn_subcategory", "subcategory"),
        Index("ix_txn_merchant", "merchant"),
        Index("ix_txn_raw_category", "raw_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Millisecond timestamp from Money Manager. Identifies an entry across exports.
    txn_ts: Mapped[datetime] = mapped_column(DateTime)
    # 0 for almost every row; separates entries that share a timestamp.
    dup_seq: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(10))  # expense | income | transfer
    direction: Mapped[str] = mapped_column(String(10))  # as exported: expense | income
    amount: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(100))
    raw_category: Mapped[str] = mapped_column(String(100))
    subcategory: Mapped[str | None] = mapped_column(String(50))
    merchant: Mapped[str | None] = mapped_column(String(200))
    note_raw: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # Read out of the description at import ("15983 kms"); NULL when there is none.
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(40))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    last_import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))


class DashboardTile(Base):
    """A pinned question. Holds the query (with date placeholders when rolling), never the numbers."""

    __tablename__ = "dashboard_tiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    title: Mapped[str] = mapped_column(String(120))
    question: Mapped[str] = mapped_column(Text)
    sql: Mapped[str] = mapped_column(Text)
    chart: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer, default=0)


ACCOUNT_TYPES = ("cash", "equity", "mutual_fund", "debt", "other")


class Account(Base):
    """Somewhere money sits: a bank account, a broker, a fund house, PF. Typed by what it holds."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # one of ACCOUNT_TYPES
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)


class Snapshot(Base):
    """What an account was worth on a day, typed in by hand. One per account per day."""

    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("account_id", "as_of", name="uq_snapshot_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)  # current worth
    invested: Mapped[float | None] = mapped_column(Float)  # amount put in, when known
    note: Mapped[str | None] = mapped_column(String(200))


class Card(Base):
    """A credit card, tracked by hand: which day its bill is generated and how long you have to pay it."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    statement_day: Mapped[int] = mapped_column(Integer)  # day of month the bill is generated, 1-31
    due_days: Mapped[int | None] = mapped_column(Integer)  # days from statement to due date, when it is fixed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)


class Bill(Base):
    """One generated statement for a card. The amount is what the bill said, typed in."""

    __tablename__ = "bills"
    __table_args__ = (UniqueConstraint("card_id", "statement_date", name="uq_bill_statement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    statement_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)  # total amount due
    min_due: Mapped[float | None] = mapped_column(Float)
    due_date: Mapped[date | None] = mapped_column(Date)
    paid_on: Mapped[date | None] = mapped_column(Date)

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    content_hash: Mapped[str] = mapped_column(String(40))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))
    last_import_id: Mapped[int] = mapped_column(ForeignKey("imports.id"))

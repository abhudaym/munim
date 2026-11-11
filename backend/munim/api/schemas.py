from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Kind = Literal["expense", "income", "transfer"]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_ts: datetime
    kind: str
    amount: float
    category: str
    subcategory: str | None
    merchant: str | None
    note_raw: str | None
    description: str | None
    deleted_at: datetime | None


class TransactionPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TransactionOut]


class SummaryRow(BaseModel):
    key: str
    total: float
    count: int


class Summary(BaseModel):
    group_by: str
    total: float
    count: int
    rows: list[SummaryRow]


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    sha256: str
    range_start: datetime | None
    range_end: datetime | None
    imported_at: datetime
    rows_in_file: int
    n_new: int
    n_updated: int
    n_deleted: int
    n_unchanged: int


class CategoryMapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw_category: str
    category: str
    kind: str | None


class CategoryMapPatch(BaseModel):
    category: str | None = None
    # Send "" to clear the override and fall back to each row's own direction.
    kind: Kind | Literal[""] | None = None

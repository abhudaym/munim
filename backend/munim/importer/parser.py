"""Read a Money Manager xlsx export into plain rows. No database here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from munim.importer.normalise import content_hash, split_note

SHEET = "Money Manager"
REQUIRED = ["Date", "Category", "INR", "Income/Expense"]


class ImportFormatError(ValueError):
    """The file is not a Money Manager export we can read."""


@dataclass(frozen=True)
class ParsedRow:
    txn_ts: datetime
    amount: float
    raw_category: str
    direction: str  # expense | income
    note_raw: str | None
    description: str | None
    subcategory: str | None
    merchant: str | None
    content_hash: str


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    skipped: int


def _text(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def parse_workbook(path: str | Path) -> ParseResult:
    try:
        xl = pd.ExcelFile(path)
    except Exception as exc:  # corrupt file, wrong format
        raise ImportFormatError(f"Could not open the file as xlsx: {exc}") from exc

    sheet = SHEET if SHEET in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ImportFormatError(
            f"Sheet '{sheet}' is missing columns {missing}. Found: {[str(c) for c in df.columns]}"
        )

    rows: list[ParsedRow] = []
    skipped = 0
    for rec in df.to_dict("records"):
        ts = pd.to_datetime(rec["Date"], errors="coerce")
        amount = rec["INR"]
        raw_category = _text(rec["Category"])
        if pd.isna(ts) or pd.isna(amount) or raw_category is None:
            skipped += 1
            continue

        # Exports carry millisecond precision; rounding removes float noise from Excel.
        txn_ts = ts.round("ms").to_pydatetime()
        amount = round(float(amount), 2)
        direction = "income" if str(rec["Income/Expense"]).strip().lower() == "income" else "expense"
        note_raw = _text(rec.get("Note"))
        description = _text(rec.get("Description"))
        subcategory, merchant = split_note(note_raw)

        rows.append(
            ParsedRow(
                txn_ts=txn_ts,
                amount=amount,
                raw_category=raw_category,
                direction=direction,
                note_raw=note_raw,
                description=description,
                subcategory=subcategory,
                merchant=merchant,
                content_hash=content_hash(amount, raw_category, direction, note_raw, description),
            )
        )
    return ParseResult(rows=rows, skipped=skipped)

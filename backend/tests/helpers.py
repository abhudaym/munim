from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

HEADER = [
    "Date", "Account", "Category", "Subcategory", "Note", "INR",
    "Income/Expense", "Description", "Amount", "Currency", "Account",
]
BASE = datetime(2026, 3, 1, 9, 0, 0, 123000)


def ts(day: int, hour: int = 12, ms: int = 0) -> datetime:
    return BASE.replace(hour=hour, microsecond=ms * 1000) + timedelta(days=day - 1)


def row(day, category, note, amount, kind="Expense", description=None, hour=12, ms=0) -> dict:
    return dict(ts=ts(day, hour, ms), category=category, note=note, amount=amount,
                kind=kind, description=description)


def make_xlsx(path: Path, rows: list[dict], sheet: str = "Money Manager") -> Path:
    """Write a file shaped like a Money Manager export (note the duplicate 'Account' header)."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(HEADER)
    for r in rows:
        ws.append([
            r["ts"], "Accounts", r["category"], None, r.get("note"), r["amount"],
            r.get("kind", "Expense"), r.get("description"), r["amount"], "INR", r["amount"],
        ])
    wb.save(path)
    return path


def sample_rows() -> list[dict]:
    """Five days of entries, newest first like the real export."""
    return [
        row(5, "Food 🍕", "Coffee: blue tokai", 280),
        row(4, "Garage", "Petrol", 2000, description="Car\n15000 kms"),
        row(3, "Investments", "Sip", 40000),
        row(2, "Salary", None, 198000, kind="Income"),
        row(1, "Food 🍕", "Eatout: mcd", 250),
    ]

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


class FakeLLM:
    """Scripted stand-in for the model. Records what it was asked."""

    name = "fake-model"

    def __init__(self, *drafts):
        self.drafts = list(drafts)
        self.calls: list[dict] = []

    def write_query(self, question, context, previous=None):
        self.calls.append({"question": question, "context": context, "previous": previous})
        draft = self.drafts.pop(0)
        if isinstance(draft, Exception):
            raise draft
        return draft


def ask_rows() -> list[dict]:
    """Feb to Apr 2026. Expenses total 4890 once the deleted petrol entry (day 20) is gone."""
    return [
        row(33, "Food 🍕", "Coffee: blue tokai", 290),  # 2 Apr
        row(20, "Garage", "Petrol", 2100),  # deleted again by the second import
        row(12, "Food 🍕", "Coffee: blue tokai", 320),
        row(11, "Salary", None, 198000, kind="Income"),
        row(10, "Investments", "Sip", 40000),
        row(8, "Garage", "Petrol", 2000),
        row(6, "Food 🍕", "Eatout: paul's", 1200),
        row(5, "Food 🍕", "Eatout: mcd", 250),
        row(3, "Food 🍕", "Coffee: blue tokai", 280),
        row(-2, "Food 🍕", "Coffee: third wave", 250),  # 27 Feb
        row(-9, "Food 🍕", "Coffee: blue tokai", 300),  # 20 Feb
    ]


def sample_rows() -> list[dict]:
    """Five days of entries, newest first like the real export."""
    return [
        row(5, "Food 🍕", "Coffee: blue tokai", 280),
        row(4, "Garage", "Petrol", 2000, description="Car\n15000 kms"),
        row(3, "Investments", "Sip", 40000),
        row(2, "Salary", None, 198000, kind="Income"),
        row(1, "Food 🍕", "Eatout: mcd", 250),
    ]

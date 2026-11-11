"""Small pure functions that turn raw Money Manager values into clean ones."""

from __future__ import annotations

import hashlib
import re

# Categories that move money between your own pockets rather than spend it.
# Applied only when a raw category is seen for the first time; editable afterwards.
SEED_KINDS = {"investments": "transfer", "emi": "transfer"}

_KEEP = re.compile(r"[^\w\s&/+-]")
_SPACES = re.compile(r"\s+")


def clean_category(raw: str) -> str:
    """'Food 🍕' -> 'Food'. Falls back to the raw text if nothing is left."""
    cleaned = _SPACES.sub(" ", _KEEP.sub("", raw)).strip()
    return cleaned or raw.strip()


def split_note(note: str | None) -> tuple[str | None, str | None]:
    """'Coffee: blue tokai' -> ('coffee', 'blue tokai'); 'Petrol' -> (None, 'petrol').

    Only a short prefix counts as a subcategory, so a long sentence that happens
    to contain a colon is kept whole as the merchant.
    """
    if not note:
        return None, None
    text = note.strip()
    if ":" in text:
        prefix, rest = text.split(":", 1)
        prefix, rest = prefix.strip(), rest.strip()
        if prefix and len(prefix) <= 24 and rest:
            return prefix.lower(), rest.lower()
    return None, text.lower() or None


def content_hash(
    amount: float,
    raw_category: str,
    direction: str,
    note_raw: str | None,
    description: str | None,
) -> str:
    """Fingerprint of everything that can change when you edit an entry.

    The timestamp is deliberately not part of it: the timestamp finds the row,
    the hash says whether its content changed.
    """
    parts = [f"{amount:.2f}", raw_category, direction, note_raw or "", description or ""]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


def derive_kind(direction: str, map_kind: str | None) -> str:
    return map_kind or direction

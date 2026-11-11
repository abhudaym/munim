"""Diff an export against the database, then apply the diff.

Rules, inside the file's own date range only:
  * timestamp not in DB            -> insert
  * timestamp in DB, same hash     -> unchanged
  * timestamp in DB, hash differs  -> update (you edited the entry)
  * row in DB, absent from file    -> soft delete (you deleted it in the app)
  * soft-deleted row back in file  -> restored
Entries that share a timestamp are matched by hash first, then paired in order.
Rows outside the file's range are never touched, so older exports stay valid.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from munim.db.models import CategoryMap, Import, Transaction, utcnow
from munim.importer.normalise import SEED_KINDS, clean_category, derive_kind
from munim.importer.parser import ParsedRow, parse_workbook

SAMPLE_LIMIT = 25


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", Path(name).name) or "upload.xlsx"


@dataclass
class Plan:
    rows_in_file: int = 0
    skipped_rows: int = 0
    range_start: datetime | None = None
    range_end: datetime | None = None
    inserts: list[tuple[ParsedRow, int]] = field(default_factory=list)
    updates: list[tuple[Transaction, ParsedRow]] = field(default_factory=list)
    deletes: list[Transaction] = field(default_factory=list)
    unchanged: int = 0
    new_categories: list[str] = field(default_factory=list)
    already_imported: bool = False

    @property
    def n_new(self) -> int:
        return len(self.inserts)

    @property
    def n_updated(self) -> int:
        return len(self.updates)

    @property
    def n_deleted(self) -> int:
        return len(self.deletes)

    @property
    def is_noop(self) -> bool:
        return not (self.inserts or self.updates or self.deletes)

    def summary(self) -> dict:
        """JSON-friendly description. Call before apply_plan, while the old values are still loaded."""

        def row_dict(r: ParsedRow) -> dict:
            return {
                "txn_ts": r.txn_ts.isoformat(),
                "amount": r.amount,
                "category": clean_category(r.raw_category),
                "note": r.note_raw,
            }

        def txn_dict(t: Transaction) -> dict:
            return {
                "txn_ts": t.txn_ts.isoformat(),
                "amount": t.amount,
                "category": t.category,
                "note": t.note_raw,
            }

        return {
            "rows_in_file": self.rows_in_file,
            "skipped_rows": self.skipped_rows,
            "range_start": self.range_start.isoformat() if self.range_start else None,
            "range_end": self.range_end.isoformat() if self.range_end else None,
            "new": self.n_new,
            "updated": self.n_updated,
            "deleted": self.n_deleted,
            "unchanged": self.unchanged,
            "new_categories": self.new_categories,
            "already_imported": self.already_imported,
            "samples": {
                "new": [row_dict(r) for r, _ in self.inserts[:SAMPLE_LIMIT]],
                "updated": [
                    {**row_dict(r), "was": txn_dict(t), "restored": t.deleted_at is not None}
                    for t, r in self.updates[:SAMPLE_LIMIT]
                ],
                "deleted": [txn_dict(t) for t in self.deletes[:SAMPLE_LIMIT]],
            },
        }


def build_plan(session: Session, rows: list[ParsedRow], skipped: int = 0) -> Plan:
    plan = Plan(rows_in_file=len(rows), skipped_rows=skipped)
    known = set(session.scalars(select(CategoryMap.raw_category)))
    plan.new_categories = sorted({r.raw_category for r in rows} - known)
    if not rows:
        return plan

    plan.range_start = min(r.txn_ts for r in rows)
    plan.range_end = max(r.txn_ts for r in rows)

    db_by_ts: dict[datetime, list[Transaction]] = defaultdict(list)
    in_range = select(Transaction).where(
        Transaction.txn_ts >= plan.range_start, Transaction.txn_ts <= plan.range_end
    )
    for t in session.scalars(in_range):
        db_by_ts[t.txn_ts].append(t)

    file_by_ts: dict[datetime, list[ParsedRow]] = defaultdict(list)
    for r in rows:
        file_by_ts[r.txn_ts].append(r)

    for ts, frows in file_by_ts.items():
        drows = sorted(db_by_ts.pop(ts, []), key=lambda t: t.dup_seq)
        used_seqs = {d.dup_seq for d in drows}
        available = list(drows)
        unmatched: list[ParsedRow] = []

        for f in frows:  # identical content first
            match = next((d for d in available if d.content_hash == f.content_hash), None)
            if match is None:
                unmatched.append(f)
                continue
            available.remove(match)
            if match.deleted_at is not None:
                plan.updates.append((match, f))  # came back: restore
            else:
                plan.unchanged += 1

        # Leftovers at this timestamp: a live row that changed is an edit.
        available.sort(key=lambda d: (d.deleted_at is not None, d.dup_seq))
        for f in unmatched:
            if available:
                plan.updates.append((available.pop(0), f))
                continue
            seq = 0
            while seq in used_seqs:
                seq += 1
            used_seqs.add(seq)
            plan.inserts.append((f, seq))

        plan.deletes.extend(d for d in available if d.deleted_at is None)

    for leftovers in db_by_ts.values():  # timestamps the file no longer has
        plan.deletes.extend(d for d in leftovers if d.deleted_at is None)

    plan.deletes.sort(key=lambda t: t.txn_ts, reverse=True)
    return plan


def _fields(row: ParsedRow, cmap: dict[str, CategoryMap]) -> dict:
    entry = cmap[row.raw_category]
    return {
        "kind": derive_kind(row.direction, entry.kind),
        "direction": row.direction,
        "amount": row.amount,
        "category": entry.category,
        "raw_category": row.raw_category,
        "subcategory": row.subcategory,
        "merchant": row.merchant,
        "note_raw": row.note_raw,
        "description": row.description,
        "content_hash": row.content_hash,
    }


def apply_plan(session: Session, plan: Plan, imp: Import) -> None:
    for raw in plan.new_categories:
        clean = clean_category(raw)
        session.add(CategoryMap(raw_category=raw, category=clean, kind=SEED_KINDS.get(clean.lower())))
    session.flush()
    cmap = {c.raw_category: c for c in session.scalars(select(CategoryMap))}

    for row, seq in plan.inserts:
        session.add(
            Transaction(
                txn_ts=row.txn_ts,
                dup_seq=seq,
                first_import_id=imp.id,
                last_import_id=imp.id,
                **_fields(row, cmap),
            )
        )
    for txn, row in plan.updates:
        for key, value in _fields(row, cmap).items():
            setattr(txn, key, value)
        txn.deleted_at = None
        txn.last_import_id = imp.id
    now = utcnow()
    for txn in plan.deletes:
        txn.deleted_at = now
        txn.last_import_id = imp.id
    session.flush()


def _plan_for(session: Session, path: Path) -> tuple[Plan, str]:
    parsed = parse_workbook(path)
    plan = build_plan(session, parsed.rows, parsed.skipped)
    sha = file_sha256(path)
    seen = session.scalar(select(func.count()).select_from(Import).where(Import.sha256 == sha))
    plan.already_imported = bool(seen)
    return plan, sha


def preview_import(session: Session, path: str | Path) -> dict:
    """Dry run. Reads the DB, writes nothing."""
    plan, sha = _plan_for(session, Path(path))
    return {"sha256": sha, **plan.summary()}


def archive_file(path: Path, filename: str, sha: str, data_dir: Path) -> Path:
    raw = data_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    dest = raw / f"{sha[:12]}_{safe_filename(filename)}"
    if not dest.exists():
        shutil.copy2(path, dest)
    return dest


def commit_import(session: Session, path: str | Path, filename: str, data_dir: Path) -> tuple[Import, dict]:
    """Archive the file, apply the diff, record the import. One transaction."""
    path = Path(path)
    plan, sha = _plan_for(session, path)
    summary = {"sha256": sha, **plan.summary()}
    try:
        archive_file(path, filename, sha, data_dir)
        imp = Import(
            filename=safe_filename(filename),
            sha256=sha,
            range_start=plan.range_start,
            range_end=plan.range_end,
            rows_in_file=plan.rows_in_file,
            n_new=plan.n_new,
            n_updated=plan.n_updated,
            n_deleted=plan.n_deleted,
            n_unchanged=plan.unchanged,
        )
        session.add(imp)
        session.flush()
        apply_plan(session, plan, imp)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return imp, summary

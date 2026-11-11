from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, literal, select, update
from sqlalchemy.orm import Session

from munim.api.deps import get_data_dir, get_session
from munim.api.schemas import (
    CategoryMapOut,
    CategoryMapPatch,
    ImportOut,
    Summary,
    SummaryRow,
    TransactionOut,
    TransactionPage,
)
from munim.db import CategoryMap, Import, Transaction
from munim.importer import ImportFormatError, commit_import, preview_import
from munim.importer.service import safe_filename

router = APIRouter(prefix="/api")

MAX_UPLOAD = 25 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------- imports

def _staging(data_dir: Path) -> Path:
    path = data_dir / "raw" / "staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _stage_upload(file: UploadFile, data_dir: Path) -> tuple[Path, str]:
    import hashlib

    body = await file.read(MAX_UPLOAD + 1)
    if len(body) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 25 MB")
    sha = hashlib.sha256(body).hexdigest()
    dest = _staging(data_dir) / f"{sha}__{safe_filename(file.filename or 'upload.xlsx')}"
    dest.write_bytes(body)
    return dest, sha


def _find_staged(data_dir: Path, sha: str) -> Path:
    if not SHA.match(sha):
        raise HTTPException(404, "Unknown upload")
    found = next(_staging(data_dir).glob(f"{sha}__*"), None)
    if found is None:
        raise HTTPException(404, "Upload not found. Upload the file again.")
    return found


def _original_name(staged: Path) -> str:
    return staged.name.split("__", 1)[1]


@router.post("/imports")
async def upload_import(
    file: UploadFile = File(...),
    dry_run: bool = True,
    session: Session = Depends(get_session),
    data_dir: Path = Depends(get_data_dir),
):
    """Upload an xlsx. With dry_run (default) returns the diff and writes nothing to the DB."""
    staged, _ = await _stage_upload(file, data_dir)
    try:
        if dry_run:
            return {"committed": False, **preview_import(session, staged)}
        imp, summary = commit_import(session, staged, _original_name(staged), data_dir)
        staged.unlink(missing_ok=True)
        return {"committed": True, "import_id": imp.id, **summary}
    except ImportFormatError as exc:
        staged.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc


@router.post("/imports/{sha256}/commit")
def commit_staged(
    sha256: str,
    session: Session = Depends(get_session),
    data_dir: Path = Depends(get_data_dir),
):
    """Apply a previewed upload. The diff is recomputed against the DB as it is now."""
    staged = _find_staged(data_dir, sha256)
    try:
        imp, summary = commit_import(session, staged, _original_name(staged), data_dir)
    except ImportFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    staged.unlink(missing_ok=True)
    return {"committed": True, "import_id": imp.id, **summary}


@router.get("/imports", response_model=list[ImportOut])
def list_imports(session: Session = Depends(get_session)):
    return session.scalars(select(Import).order_by(Import.id.desc()).limit(50)).all()


# ------------------------------------------------------------ transactions

def _filters(
    stmt,
    date_from: date | None,
    date_to: date | None,
    kind: str | None,
    category: str | None,
    subcategory: str | None,
    merchant: str | None,
    q: str | None,
    include_deleted: bool = False,
):
    if not include_deleted:
        stmt = stmt.where(Transaction.deleted_at.is_(None))
    if date_from:
        stmt = stmt.where(Transaction.txn_ts >= datetime.combine(date_from, time.min))
    if date_to:  # inclusive of the whole day
        stmt = stmt.where(Transaction.txn_ts < datetime.combine(date_to + timedelta(days=1), time.min))
    if kind and kind != "all":
        stmt = stmt.where(Transaction.kind == kind)
    if category:
        stmt = stmt.where(Transaction.category == category)
    if subcategory:
        stmt = stmt.where(Transaction.subcategory == subcategory.lower())
    if merchant:
        stmt = stmt.where(Transaction.merchant == merchant.lower())
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(Transaction.merchant, "")).like(like)
            | func.lower(func.coalesce(Transaction.note_raw, "")).like(like)
            | func.lower(Transaction.category).like(like)
            | func.lower(func.coalesce(Transaction.subcategory, "")).like(like)
        )
    return stmt


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    kind: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    merchant: str | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    args = (date_from, date_to, kind, category, subcategory, merchant, q, include_deleted)
    total = session.scalar(_filters(select(func.count()).select_from(Transaction), *args))
    items = session.scalars(
        _filters(select(Transaction), *args)
        .order_by(Transaction.txn_ts.desc(), Transaction.dup_seq.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return TransactionPage(total=total or 0, limit=limit, offset=offset, items=items)


# ----------------------------------------------------------------- summary

@router.get("/summary", response_model=Summary)
def summary(
    group_by: Literal["category", "subcategory", "merchant", "month"] = "category",
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    kind: str = "expense",
    session: Session = Depends(get_session),
):
    """Totals for one kind (default: expense; transfers like SIPs and EMIs are excluded)."""
    columns = {
        "category": Transaction.category,
        "subcategory": Transaction.subcategory,
        "merchant": Transaction.merchant,
        "month": func.strftime("%Y-%m", Transaction.txn_ts),
    }
    key = columns[group_by]
    total = func.sum(Transaction.amount)
    stmt = _filters(
        select(key, total, func.count()), date_from, date_to, kind, None, None, None, None
    ).group_by(key)
    stmt = stmt.order_by(key.asc() if group_by == "month" else total.desc())

    rows = [
        SummaryRow(key=k if k is not None else "(none)", total=round(t or 0, 2), count=c)
        for k, t, c in session.execute(stmt)
    ]
    return Summary(
        group_by=group_by,
        total=round(sum(r.total for r in rows), 2),
        count=sum(r.count for r in rows),
        rows=rows,
    )


# ------------------------------------------------------------ category map

@router.get("/category-map", response_model=list[CategoryMapOut])
def get_category_map(session: Session = Depends(get_session)):
    return session.scalars(select(CategoryMap).order_by(CategoryMap.category)).all()


@router.patch("/category-map/{raw_category}", response_model=CategoryMapOut)
def patch_category_map(
    raw_category: str,
    body: CategoryMapPatch,
    session: Session = Depends(get_session),
):
    """Rename a category or change its kind, and re-apply it to every stored transaction."""
    entry = session.get(CategoryMap, raw_category)
    if entry is None:
        raise HTTPException(404, "Unknown category")

    values: dict = {}
    if body.category is not None:
        name = body.category.strip()
        if not name:
            raise HTTPException(422, "Category name cannot be empty")
        entry.category = name
        values["category"] = name
    if body.kind is not None:
        entry.kind = body.kind or None
        values["kind"] = func.coalesce(literal(entry.kind), Transaction.direction)

    if values:
        session.execute(
            update(Transaction).where(Transaction.raw_category == raw_category).values(**values)
        )
    session.commit()
    return entry

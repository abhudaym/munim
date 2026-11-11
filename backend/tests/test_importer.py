from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import func, select

from munim.db import CategoryMap, Import, Transaction
from munim.importer import ImportFormatError, commit_import, parse_workbook, preview_import
from tests.helpers import make_xlsx, row, sample_rows, ts


def run(session, tmp_path, data_dir, rows, name="export.xlsx"):
    path = make_xlsx(tmp_path / name, rows)
    imp, summary = commit_import(session, path, name, data_dir)
    return imp, summary


def live(session):
    return list(session.scalars(
        select(Transaction).where(Transaction.deleted_at.is_(None)).order_by(Transaction.txn_ts)
    ))


def test_first_import_inserts_everything(session, tmp_path, data_dir):
    _, s = run(session, tmp_path, data_dir, sample_rows())
    assert (s["new"], s["updated"], s["deleted"], s["unchanged"]) == (5, 0, 0, 0)
    assert len(live(session)) == 5


def test_reimporting_same_file_changes_nothing(session, tmp_path, data_dir):
    run(session, tmp_path, data_dir, sample_rows())
    _, s = run(session, tmp_path, data_dir, sample_rows(), name="again.xlsx")
    assert (s["new"], s["updated"], s["deleted"], s["unchanged"]) == (0, 0, 0, 5)
    assert s["already_imported"] is True
    assert session.scalar(select(func.count()).select_from(Transaction)) == 5


def test_preview_writes_nothing(session, tmp_path):
    path = make_xlsx(tmp_path / "p.xlsx", sample_rows())
    result = preview_import(session, path)
    assert result["new"] == 5
    assert session.scalar(select(func.count()).select_from(Transaction)) == 0
    assert session.scalar(select(func.count()).select_from(Import)) == 0
    assert session.scalar(select(func.count()).select_from(CategoryMap)) == 0


def test_overlapping_files_only_add_the_new_rows(session, tmp_path, data_dir):
    first = [row(d, "Food 🍕", f"Eatout: a{d}", 100 + d) for d in range(10, 0, -1)]
    second = [row(d, "Food 🍕", f"Eatout: a{d}", 100 + d) for d in range(15, 4, -1)]  # days 5..15
    run(session, tmp_path, data_dir, first)
    _, s = run(session, tmp_path, data_dir, second, name="week2.xlsx")
    assert s["new"] == 5 and s["unchanged"] == 6 and s["updated"] == 0 and s["deleted"] == 0
    assert len(live(session)) == 15


def test_edited_entry_is_an_update_not_a_duplicate(session, tmp_path, data_dir):
    run(session, tmp_path, data_dir, sample_rows())
    edited = sample_rows()
    edited[0] = row(5, "Food 🍕", "Coffee: blue tokai", 305)  # amount changed in the app
    _, s = run(session, tmp_path, data_dir, edited, name="edited.xlsx")
    assert (s["new"], s["updated"], s["deleted"], s["unchanged"]) == (0, 1, 0, 4)
    assert s["samples"]["updated"][0]["was"]["amount"] == 280
    coffee = [t for t in live(session) if t.subcategory == "coffee"]
    assert [t.amount for t in coffee] == [305]


def test_entry_removed_in_app_is_soft_deleted(session, tmp_path, data_dir):
    run(session, tmp_path, data_dir, sample_rows())
    # Remove a middle entry so the file's date range stays the same.
    trimmed = [r for r in sample_rows() if r["category"] != "Garage"]
    _, s = run(session, tmp_path, data_dir, trimmed, name="trimmed.xlsx")
    assert (s["new"], s["updated"], s["deleted"], s["unchanged"]) == (0, 0, 1, 4)
    gone = session.scalars(select(Transaction).where(Transaction.deleted_at.is_not(None))).all()
    assert [t.category for t in gone] == ["Garage"]
    assert len(live(session)) == 4


def test_rows_outside_the_files_range_are_untouched(session, tmp_path, data_dir):
    run(session, tmp_path, data_dir, sample_rows())  # days 1..5
    later = [row(20, "Food 🍕", "Coffee: x", 100), row(19, "Food 🍕", "Coffee: y", 120)]
    _, s = run(session, tmp_path, data_dir, later, name="later.xlsx")
    assert s["deleted"] == 0 and s["new"] == 2
    assert len(live(session)) == 7


def test_deleted_entry_that_returns_is_restored(session, tmp_path, data_dir):
    run(session, tmp_path, data_dir, sample_rows())
    run(session, tmp_path, data_dir, [r for r in sample_rows() if r["category"] != "Garage"], name="b.xlsx")
    _, s = run(session, tmp_path, data_dir, sample_rows(), name="c.xlsx")
    assert s["updated"] == 1 and s["new"] == 0
    assert s["samples"]["updated"][0]["restored"] is True
    assert len(live(session)) == 5


def test_same_timestamp_rows_both_survive(session, tmp_path, data_dir):
    rows = [row(3, "Apparel 👕", "Backpack", 3546, ms=763), row(3, "Garage", "Petrol", 3532, ms=763)]
    _, s = run(session, tmp_path, data_dir, rows)
    assert s["new"] == 2
    stored = sorted(live(session), key=lambda t: t.dup_seq)
    assert [t.dup_seq for t in stored] == [0, 1]
    assert stored[0].txn_ts == stored[1].txn_ts
    # and they are stable on re-import, in any order
    _, again = run(session, tmp_path, data_dir, list(reversed(rows)), name="again.xlsx")
    assert (again["new"], again["updated"], again["deleted"], again["unchanged"]) == (0, 0, 0, 2)


def test_edit_one_of_two_same_timestamp_rows(session, tmp_path, data_dir):
    rows = [row(3, "Apparel 👕", "Backpack", 3546, ms=763), row(3, "Garage", "Petrol", 3532, ms=763)]
    run(session, tmp_path, data_dir, rows)
    edited = [row(3, "Apparel 👕", "Backpack", 3546, ms=763), row(3, "Garage", "Petrol", 3600, ms=763)]
    _, s = run(session, tmp_path, data_dir, edited, name="e.xlsx")
    assert (s["new"], s["updated"], s["deleted"], s["unchanged"]) == (0, 1, 0, 1)
    assert sorted(t.amount for t in live(session)) == [3546, 3600]


def test_fields_are_normalised(session, tmp_path, data_dir):
    run(session, tmp_path, data_dir, sample_rows())
    by_note = {t.note_raw: t for t in live(session)}
    coffee = by_note["Coffee: blue tokai"]
    assert (coffee.category, coffee.subcategory, coffee.merchant) == ("Food", "coffee", "blue tokai")
    assert coffee.raw_category == "Food 🍕" and coffee.kind == "expense"
    petrol = by_note["Petrol"]
    assert petrol.subcategory is None and petrol.merchant == "petrol"
    assert petrol.description == "Car\n15000 kms"
    assert by_note["Sip"].kind == "transfer"
    salary = next(t for t in live(session) if t.category == "Salary")
    assert salary.kind == "income" and salary.merchant is None and salary.note_raw is None


def test_import_history_is_recorded_and_file_archived(session, tmp_path, data_dir):
    imp, _ = run(session, tmp_path, data_dir, sample_rows())
    assert imp.n_new == 5 and imp.rows_in_file == 5
    assert imp.range_start == ts(1) and imp.range_end == ts(5)
    assert len(list((data_dir / "raw").glob("*_export.xlsx"))) == 1


def test_rows_missing_required_values_are_skipped(session, tmp_path, data_dir):
    rows = sample_rows() + [dict(ts=None, category="Food", note="x", amount=1)]
    path = make_xlsx(tmp_path / "x.xlsx", rows)
    parsed = parse_workbook(path)
    assert len(parsed.rows) == 5 and parsed.skipped == 1


def test_wrong_file_gives_a_clear_error(tmp_path):
    path = tmp_path / "bad.xlsx"
    path.write_text("not an xlsx")
    with pytest.raises(ImportFormatError):
        parse_workbook(path)


def test_missing_columns_are_named(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["Date", "Foo"])
    wb.save(tmp_path / "cols.xlsx")
    with pytest.raises(ImportFormatError, match="Category"):
        parse_workbook(tmp_path / "cols.xlsx")


REAL = os.environ.get("MUNIM_SAMPLE_XLSX")


@pytest.mark.skipif(not REAL or not Path(REAL).is_file(), reason="set MUNIM_SAMPLE_XLSX to run")
def test_real_export_matches_the_plan(session, data_dir):
    _, s = commit_import(session, REAL, "real.xlsx", data_dir)
    assert s["new"] == s["rows_in_file"]
    counts = dict(session.execute(
        select(Transaction.subcategory, func.count()).where(Transaction.subcategory.is_not(None)).group_by(Transaction.subcategory)
    ).all())
    assert set(counts) == {"coffee", "eatout", "delivery"}
    _, again = commit_import(session, REAL, "real.xlsx", data_dir)
    assert (again["new"], again["updated"], again["deleted"]) == (0, 0, 0)

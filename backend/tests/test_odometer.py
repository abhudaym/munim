import sqlite3
from datetime import date

import pytest

from munim.ask import Draft, ask
from munim.ask.context import build_context
from munim.ask.runner import connect_readonly
from munim.db import init_db, make_engine
from munim.db.session import make_session_factory
from munim.importer import commit_import
from munim.importer.normalise import extract_odometer
from tests.helpers import FakeLLM, make_xlsx, row


@pytest.mark.parametrize(
    "text,km",
    [
        ("Xp95\n15983 kms", 15983),
        ("Xp95 \n14241 km", 14241),
        ("XP95 9100KMS", 9100),
        ("odo 1,02,340 km", 102340),
        ("12,814 kms", 12814),
        ("15151 kilometres", 15151),
        ("Xp95", None),
        ("Jaipur trip (112 per litre)", None),
        ("Full tank for jaipur trip", None),
        ("5 km from home", None),
        ("room 1500 kmart", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_odometer(text, km):
    assert extract_odometer(text) == km


def fuel_rows():
    return [
        row(30, "Garage", "Petrol", 3000, description="Xp95\n15983 kms"),
        row(20, "Garage", "Petrol", 2500, description="Xp95 \n15418 km"),
        row(12, "Garage", "Petrol", 3000, description="Full tank for jaipur trip"),
        row(5, "Garage", "Petrol", 2000, description="Xp95\n14611 kms"),
        row(1, "Garage", "Petrol", 2000, description="Xp95"),
        row(3, "Food 🍕", "Coffee: blue tokai", 300),
    ]


@pytest.fixture()
def fuel_db(session, tmp_path, data_dir):
    commit_import(session, make_xlsx(tmp_path / "f.xlsx", fuel_rows()), "f.xlsx", data_dir)
    return data_dir / "munim.db"


def test_import_fills_the_column_and_an_edit_updates_it(session, tmp_path, data_dir, fuel_db):
    read = lambda: sqlite3.connect(fuel_db).execute(  # noqa: E731
        "SELECT odometer_km FROM transactions ORDER BY txn_ts"
    ).fetchall()
    assert [r[0] for r in read()] == [None, None, 14611, None, 15418, 15983]

    rows = fuel_rows()
    rows[0]["description"] = "Xp95\n16001 kms"  # corrected in the app, same timestamp
    commit_import(session, make_xlsx(tmp_path / "g.xlsx", rows), "g.xlsx", data_dir)
    assert read()[-1][0] == 16001


def test_distance_is_last_minus_first_not_a_sum(fuel_db, session):
    sql = (
        "SELECT sum(amount) AS spent, max(odometer_km) - min(odometer_km) AS km_driven "
        "FROM v_expenses WHERE merchant LIKE '%petrol%'"
    )
    out = ask("petrol and km?", db_path=fuel_db, llm=FakeLLM(Draft(sql, None)),
              session_factory=make_session_factory(session.get_bind()), today=date(2026, 4, 30))
    assert out.error is None and out.rows == [[12500.0, 1372]]


def test_distance_per_fill_up_with_a_window_function(fuel_db, session):
    sql = (
        "SELECT txn_date, odometer_km - LAG(odometer_km) OVER (ORDER BY txn_ts) AS km "
        "FROM v_expenses WHERE odometer_km IS NOT NULL ORDER BY txn_ts"
    )
    out = ask("km per fill?", db_path=fuel_db, llm=FakeLLM(Draft(sql, None)), today=date(2026, 4, 30))
    assert out.error is None and [r[1] for r in out.rows] == [None, 807, 565]


def test_model_is_told_how_far_the_readings_reach(fuel_db, db_path=None):
    conn = connect_readonly(fuel_db)
    try:
        text = build_context(conn, date(2026, 4, 30))
    finally:
        conn.close()
    assert "odometer_km:" in text and "Odometer readings: 3 entries, from" in text
    assert "15983" not in text  # the readings themselves are not sent


def test_no_readings_is_said_plainly(db_path):
    conn = connect_readonly(db_path)
    try:
        assert "Odometer readings: none recorded." in build_context(conn, date(2026, 4, 10))
    finally:
        conn.close()


def test_older_database_gains_the_column_and_is_backfilled(tmp_path):
    path = tmp_path / "old.db"
    engine = make_engine(f"sqlite:///{path}")
    init_db(engine)
    with engine.begin() as conn:  # put it back the way an older version left it
        conn.exec_driver_sql("DROP VIEW v_expenses")
        conn.exec_driver_sql("DROP VIEW v_entries")
        conn.exec_driver_sql("ALTER TABLE transactions DROP COLUMN odometer_km")
        conn.exec_driver_sql("INSERT INTO imports (id, filename, sha256, imported_at, rows_in_file, n_new, n_updated, n_deleted, n_unchanged) VALUES (1, 'x', 'y', '2026-01-01', 2, 2, 0, 0, 0)")
        for i, text in enumerate(["Xp95\n7968 kms", "Xp95"]):
            conn.exec_driver_sql(
                "INSERT INTO transactions (txn_ts, dup_seq, kind, direction, amount, category, raw_category, "
                "description, content_hash, first_import_id, last_import_id) "
                f"VALUES ('2026-04-0{i + 1} 10:00:00.000', 0, 'expense', 'expense', 100, 'Garage', 'Garage', ?, 'h', 1, 1)",
                (text,),
            )
    init_db(engine)
    init_db(engine)  # and it is safe to run again
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT odometer_km FROM v_expenses ORDER BY txn_ts").fetchall() == [(7968,), (None,)]
    engine.dispose()

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from munim.db.models import Base
from munim.db.views import create_views


def make_engine(url: str) -> Engine:
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine


def _migrate(conn) -> None:
    """Small additive changes for databases made by an older version. No Alembic yet."""
    from munim.importer.normalise import extract_odometer

    columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(transactions)")}
    if "odometer_km" not in columns:
        conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN odometer_km INTEGER")
        rows = conn.exec_driver_sql("SELECT id, description FROM transactions WHERE description IS NOT NULL")
        found = [(km, row_id) for row_id, text in rows if (km := extract_odometer(text)) is not None]
        for km, row_id in found:
            conn.exec_driver_sql("UPDATE transactions SET odometer_km = ? WHERE id = ?", (km, row_id))

    card_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(cards)")}
    for name, kind in (("color", "VARCHAR(7)"), ("last4", "VARCHAR(4)"), ("image", "VARCHAR(100)")):
        if card_columns and name not in card_columns:
            conn.exec_driver_sql(f"ALTER TABLE cards ADD COLUMN {name} {kind}")


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        _migrate(conn)
        create_views(conn)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)

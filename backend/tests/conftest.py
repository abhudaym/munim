from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from munim.api.app import create_app
from munim.db import init_db, make_engine
from munim.db.session import make_session_factory


@pytest.fixture(autouse=True)
def _no_real_model(monkeypatch):
    """No test may reach the real API, whatever the environment holds."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MUNIM_MODEL", raising=False)
    monkeypatch.delenv("MUNIM_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("MUNIM_SEND_MERCHANTS", raising=False)


@pytest.fixture()
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture()
def db_path(session, tmp_path, data_dir):
    """A database holding ask_rows(), with one entry soft-deleted."""
    from munim.importer import commit_import
    from tests.helpers import ask_rows, make_xlsx

    rows = ask_rows()
    commit_import(session, make_xlsx(tmp_path / "a.xlsx", rows), "a.xlsx", data_dir)
    trimmed = [r for r in rows if not (r["note"] == "Petrol" and r["amount"] == 2100)]
    commit_import(session, make_xlsx(tmp_path / "b.xlsx", trimmed), "b.xlsx", data_dir)
    return data_dir / "munim.db"


@pytest.fixture()
def session(data_dir):
    data_dir.mkdir()
    engine = make_engine(f"sqlite:///{data_dir / 'munim.db'}")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def client(data_dir):
    with TestClient(create_app(data_dir, load_llm_from_env=False)) as c:
        yield c

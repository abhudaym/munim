from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from munim.api.app import create_app
from munim.db import init_db, make_engine
from munim.db.session import make_session_factory


@pytest.fixture()
def data_dir(tmp_path):
    return tmp_path / "data"


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
    with TestClient(create_app(data_dir)) as c:
        yield c

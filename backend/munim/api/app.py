from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from munim import __version__, config
from munim.api.networth import router as networth_router
from munim.api.routes import router
from munim.db import init_db, make_engine
from munim.ask import SQLWriter, writer_from_env
from munim.db.session import make_session_factory


def create_app(
    data_dir: Path | None = None, llm: SQLWriter | None = None, load_llm_from_env: bool = True
) -> FastAPI:
    config.load_env()
    data = Path(data_dir) if data_dir else config.data_dir()
    data.mkdir(parents=True, exist_ok=True)

    engine = make_engine(config.db_url(data))
    init_db(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="Munim", version=__version__, lifespan=lifespan)
    app.state.data_dir = data
    app.state.session_factory = make_session_factory(engine)
    app.state.db_path = data / "munim.db"
    if llm is None and load_llm_from_env:
        llm = writer_from_env()  # None when nothing is configured
    app.state.llm = llm
    app.include_router(router)
    app.include_router(networth_router)

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    dist = config.web_dist()
    if (dist / "index.html").is_file():  # serve the built web app from the same process
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app

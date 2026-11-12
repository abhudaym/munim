"""Where Munim keeps its files. Override with MUNIM_DATA_DIR."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Read REPO_ROOT/.env into the environment. Real environment variables win."""
    path = REPO_ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def data_dir() -> Path:
    env = os.environ.get("MUNIM_DATA_DIR")
    path = Path(env).expanduser() if env else REPO_ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_url(data: Path) -> str:
    return f"sqlite:///{data / 'munim.db'}"


def web_dist() -> Path:
    return REPO_ROOT / "web" / "dist"

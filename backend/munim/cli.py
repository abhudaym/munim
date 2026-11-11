"""munim import <file.xlsx> [--dry-run]   |   munim serve"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from munim import config
from munim.db import init_db, make_engine
from munim.db.session import make_session_factory
from munim.importer import ImportFormatError, commit_import, preview_import


def _print_summary(s: dict, dry_run: bool) -> None:
    head = "Dry run (nothing written)" if dry_run else "Imported"
    print(f"{head}: {s['rows_in_file']} rows, {s['range_start']} -> {s['range_end']}")
    print(f"  new {s['new']}   updated {s['updated']}   deleted {s['deleted']}   unchanged {s['unchanged']}")
    if s["skipped_rows"]:
        print(f"  skipped {s['skipped_rows']} rows with a missing date, amount or category")
    if s["new_categories"]:
        print(f"  new categories: {', '.join(s['new_categories'])}")
    if s["already_imported"]:
        print("  note: this exact file was imported before")


def cmd_import(args: argparse.Namespace) -> int:
    data = Path(args.data_dir).expanduser() if args.data_dir else config.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    engine = make_engine(config.db_url(data))
    init_db(engine)
    path = Path(args.file).expanduser()
    if not path.is_file():
        print(f"No such file: {path}", file=sys.stderr)
        return 2
    try:
        with make_session_factory(engine)() as session:
            if args.dry_run:
                _print_summary(preview_import(session, path), dry_run=True)
            else:
                _, summary = commit_import(session, path, path.name, data)
                _print_summary(summary, dry_run=False)
    except ImportFormatError as exc:
        print(f"Cannot import: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("munim.api.app:create_app", factory=True, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="munim")
    sub = parser.add_subparsers(dest="command", required=True)

    p_imp = sub.add_parser("import", help="load a Money Manager xlsx export")
    p_imp.add_argument("file")
    p_imp.add_argument("--dry-run", action="store_true", help="show the diff, write nothing")
    p_imp.add_argument("--data-dir", help="override MUNIM_DATA_DIR")
    p_imp.set_defaults(func=cmd_import)

    p_srv = sub.add_parser("serve", help="run the API (and the built web app, if present)")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8000)
    p_srv.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

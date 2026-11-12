"""munim import <file.xlsx> [--dry-run]  |  munim serve  |  munim ask "..."  |  munim eval"""

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


def _open(args: argparse.Namespace):
    config.load_env()
    data = Path(args.data_dir).expanduser() if args.data_dir else config.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    engine = make_engine(config.db_url(data))
    init_db(engine)
    return data / "munim.db", make_session_factory(engine)


def _writer():
    from munim.ask import writer_from_env

    llm = writer_from_env()
    if llm is None:
        print("No model configured: see .env.example (MUNIM_PROVIDER)", file=sys.stderr)
    return llm


def cmd_ask(args: argparse.Namespace) -> int:
    from munim.ask import LLMError, ask

    db_path, factory = _open(args)
    llm = _writer()
    if llm is None:
        return 2
    try:
        res = ask(" ".join(args.question), db_path=db_path, llm=llm, session_factory=factory)
    except LLMError as exc:
        print(f"Model error: {exc}", file=sys.stderr)
        return 1
    if res.note:
        print(res.note)
    if res.error:
        print(f"Could not answer: {res.error}", file=sys.stderr)
    elif res.sql is None:
        pass
    elif res.headline is not None:
        print(f"{res.headline:,}")
    else:
        print(" | ".join(res.columns))
        for r in res.rows:
            print(" | ".join("" if v is None else str(v) for v in r))
        if res.truncated:
            print("(more rows than shown)")
    if args.show_sql and res.sql:
        print(f"\n{res.sql}")
    return 1 if res.error else 0


def cmd_eval(args: argparse.Namespace) -> int:
    from datetime import date

    from munim.ask.evals import run_eval

    db_path, _ = _open(args)
    llm = _writer()
    if llm is None:
        return 2
    today = date.fromisoformat(args.today) if args.today else None
    rows = run_eval(db_path, llm, today=today, limit=args.limit)
    for r in rows:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.question}" + (f"\n    {r.detail}" if r.detail else ""))
    passed = sum(r.ok for r in rows)
    print(f"\n{passed}/{len(rows)} passed")
    return 0 if passed == len(rows) else 1


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

    p_ask = sub.add_parser("ask", help="ask a question about your spending in plain English")
    p_ask.add_argument("question", nargs="+")
    p_ask.add_argument("--show-sql", action="store_true")
    p_ask.add_argument("--data-dir")
    p_ask.set_defaults(func=cmd_ask)

    p_eval = sub.add_parser("eval", help="score the model against the golden questions (real API calls)")
    p_eval.add_argument("--today", help="YYYY-MM-DD; defaults to the latest entry")
    p_eval.add_argument("--limit", type=int)
    p_eval.add_argument("--data-dir")
    p_eval.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

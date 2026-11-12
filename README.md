# Munim

Your expenses in one SQL database, with a small web app on top. Single user, runs on your own machine.

Right now it does two things: load Money Manager exports safely (re-uploading overlapping files never double counts), and browse them. Investments, bank balances and plain-English questions come next.

## Run it

```bash
# backend
cd backend
pip install -e ".[dev]"
munim import ~/Downloads/money-manager-export.xlsx      # add --dry-run to preview
munim serve                                              # http://127.0.0.1:8000

# web app (dev server with hot reload, proxies /api to the backend)
cd ../web
npm install
npm run dev                                              # http://localhost:5173

# or build it once and let `munim serve` host it
npm run build
```

Everything personal lives in `data/` (the database and the archived uploads). It is gitignored. Set `MUNIM_DATA_DIR` to keep it somewhere else.

## How re-importing works

Money Manager gives every entry a millisecond timestamp, so the timestamp identifies an entry. For each upload, inside the file's own date range:

| In the file | In the database | Result |
| --- | --- | --- |
| timestamp not present | - | insert |
| same timestamp, same content hash | present | unchanged |
| same timestamp, different content | present | update (you edited it) |
| absent | present | soft delete (you deleted it) |
| back again | soft-deleted | restored |

Rows outside the file's date range are never touched, so an older export stays valid. Entries that share a timestamp are told apart by `dup_seq` and matched by content.

Also done on the way in: emoji stripped from category names, `Coffee: blue tokai` split into subcategory `coffee` and merchant `blue tokai`, and Investments and EMI marked as transfers so they stay out of spend totals (change this under Import > Categories).

## Asking questions

`munim ask "how much did I spend on coffee in the last three months?"`, or use the **Ask** page.
Put `ANTHROPIC_API_KEY` in `.env` (see `.env.example`); `MUNIM_MODEL` picks the model.

The model only writes a query; your machine runs it. Two views are all it can see:
`v_expenses` (live spending, so transfers and income are excluded by construction) and
`v_entries` (everything). Queries are parsed and checked, then run on a read-only connection with
a table whitelist, a 5 s limit and a 500-row cap. Every question and its query is kept in the
`questions` table (never the result rows).

**What leaves this machine:** your question, category and subcategory names, merchant names used
at least 3 times (set `MUNIM_SEND_MERCHANTS=0` to withhold), and the date range. Never amounts or
individual transactions.

`munim eval` scores the model against ~20 golden questions with hand-written reference queries
(real API calls; run it by hand after changing the model or prompt).

## API

| Endpoint | Does |
| --- | --- |
| `POST /api/imports?dry_run=true` | upload an xlsx, get the diff, write nothing |
| `POST /api/imports/{sha256}/commit` | apply a previewed upload |
| `GET /api/imports` | import history |
| `GET /api/transactions` | filter by `from`, `to`, `kind`, `category`, `subcategory`, `merchant`, `q`; paginated |
| `GET /api/summary?group_by=category\|subcategory\|merchant\|month` | totals; `kind` defaults to `expense` |
| `GET /api/category-map`, `PATCH /api/category-map/{raw}` | rename a category or change its kind |

Interactive docs at `/docs` when the server is running.

## Tests

```bash
cd backend
pytest
MUNIM_SAMPLE_XLSX=/path/to/your/export.xlsx pytest   # also runs the check against your real file
```

Tests use generated files. Never commit a real export.

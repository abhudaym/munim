import { useEffect, useState } from "react";
import { api, Summary, SummaryRow, TxnPage } from "../api";
import { fmtDate, fmtTime, inr, monthLabel, Preset, PRESETS, presetRange } from "../format";

const LIMIT = 50;
const NONE = "(none)";
type GroupBy = "month" | "subcategory" | "merchant";
const GROUPS: { id: GroupBy; label: string }[] = [
  { id: "month", label: "Month" },
  { id: "subcategory", label: "Tag" },
  { id: "merchant", label: "Merchant" },
];

const optionLabel = (r: SummaryRow, none: string) => `${r.key === NONE ? none : r.key} (${r.count})`;

export default function Transactions() {
  const [preset, setPreset] = useState<Preset | "custom">("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [kind, setKind] = useState("expense");
  const [category, setCategory] = useState("");
  const [tag, setTag] = useState("");
  const [merchant, setMerchant] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState(""); // q, after a short pause
  const [offset, setOffset] = useState(0);
  const [groupBy, setGroupBy] = useState<GroupBy>("month");

  const [categories, setCategories] = useState<SummaryRow[]>([]);
  const [tags, setTags] = useState<SummaryRow[]>([]);
  const [merchants, setMerchants] = useState<SummaryRow[]>([]);
  const [breakdown, setBreakdown] = useState<Summary | null>(null);
  const [page, setPage] = useState<TxnPage | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(q);
      setOffset(0);
    }, 300);
    return () => clearTimeout(id);
  }, [q]);

  // Each dropdown lists what exists under the filters above it, with counts.
  useEffect(() => {
    let live = true;
    const base = { from, to, kind };
    Promise.all([
      api.summary({ ...base, group_by: "category" }),
      api.summary({ ...base, group_by: "subcategory", category }),
      api.summary({ ...base, group_by: "merchant", category, subcategory: tag }),
    ])
      .then(([c, t, m]) => {
        if (!live) return;
        setCategories(c.rows);
        setTags(t.rows);
        setMerchants(m.rows);
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [from, to, kind, category, tag]);

  useEffect(() => {
    let live = true;
    const filters = { from, to, kind, category, subcategory: tag, merchant, q: search };
    Promise.all([
      api.transactions({ ...filters, limit: LIMIT, offset }),
      kind === "all" ? Promise.resolve(null) : api.summary({ ...filters, group_by: groupBy }),
    ])
      .then(([p, b]) => {
        if (!live) return;
        setPage(p);
        setBreakdown(b);
        setError("");
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [from, to, kind, category, tag, merchant, search, offset, groupBy]);

  const pick = (id: Preset) => {
    const range = presetRange(id);
    setPreset(id);
    setFrom(range.from);
    setTo(range.to);
    setOffset(0);
  };
  const change = (set: (v: string) => void, also?: () => void) => (e: { target: { value: string } }) => {
    set(e.target.value);
    also?.();
    setOffset(0);
  };
  const customDate = (set: (v: string) => void) => change(set, () => setPreset("custom"));
  const reset = () => {
    pick("all");
    setKind("expense");
    setCategory("");
    setTag("");
    setMerchant("");
    setQ("");
  };

  const first = page && page.total ? offset + 1 : 0;
  const last = page ? Math.min(offset + LIMIT, page.total) : 0;
  const top = breakdown ? Math.max(...breakdown.rows.map((r) => r.total), 0) : 0;
  const rows = breakdown ? (groupBy === "month" ? breakdown.rows : breakdown.rows.slice(0, 12)) : [];
  const hidden = breakdown ? breakdown.rows.length - rows.length : 0;
  const totalLabel = kind === "income" ? "Total received" : kind === "transfer" ? "Total moved" : "Total spent";

  return (
    <>
      <h1>Transactions</h1>

      <div className="presets" role="group" aria-label="Date range">
        {PRESETS.map((p) => (
          <button type="button" key={p.id} className="preset" aria-pressed={preset === p.id} onClick={() => pick(p.id)}>
            {p.label}
          </button>
        ))}
        <label className="field">
          From
          <input type="date" value={from} onChange={customDate(setFrom)} />
        </label>
        <label className="field">
          To
          <input type="date" value={to} onChange={customDate(setTo)} />
        </label>
      </div>

      <form className="filters" onSubmit={(e) => e.preventDefault()}>
        <label className="field">
          Kind
          <select value={kind} onChange={change(setKind)}>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
            <option value="transfer">Transfer</option>
            <option value="all">All</option>
          </select>
        </label>
        <label className="field">
          Category
          <select value={category} onChange={change(setCategory, () => (setTag(""), setMerchant("")))}>
            <option value="">All</option>
            {categories.map((r) => (
              <option key={r.key} value={r.key}>{optionLabel(r, "No category")}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Tag
          <select value={tag} onChange={change(setTag, () => setMerchant(""))}>
            <option value="">All</option>
            {tags.map((r) => (
              <option key={r.key} value={r.key}>{optionLabel(r, "Untagged")}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Merchant
          <select value={merchant} onChange={change(setMerchant)}>
            <option value="">All</option>
            {merchants.map((r) => (
              <option key={r.key} value={r.key}>{optionLabel(r, "No merchant")}</option>
            ))}
          </select>
        </label>
        <label className="field" style={{ flex: "1 1 180px" }}>
          Search
          <input type="search" placeholder="any text in the note" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={reset}>Clear</button>
      </form>

      {error && <div className="banner error">{error}</div>}

      {kind === "all" ? (
        <p className="muted">Pick a kind to see totals. Adding income to spending would not mean much.</p>
      ) : (
        page && (
          <>
            <section className="stats" aria-label="Totals for these filters">
              <div className="card stat">
                <div className="muted">{totalLabel}</div>
                <div className="big">{inr(page.amount_total)}</div>
              </div>
              <div className="card stat">
                <div className="muted">Entries</div>
                <div className="big">{page.total.toLocaleString("en-IN")}</div>
              </div>
              <div className="card stat">
                <div className="muted">Average per entry</div>
                <div className="big">{page.total ? inr(Math.round(page.amount_total / page.total)) : "–"}</div>
              </div>
            </section>

            <section className="card">
              <div className="row" style={{ alignItems: "center" }}>
                <h2>Breakdown</h2>
                <div className="tabs" role="group" aria-label="Group by">
                  {GROUPS.map((g) => (
                    <button type="button" key={g.id} aria-pressed={groupBy === g.id} onClick={() => setGroupBy(g.id)}>
                      {g.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="bars">
                {rows.map((r) => (
                  <div className="bar-row" key={r.key}>
                    <span className={r.key === NONE ? "muted" : ""}>
                      {r.key === NONE ? (groupBy === "merchant" ? "no merchant" : "untagged") : groupBy === "month" ? monthLabel(r.key) : r.key}
                    </span>
                    <span className="track" aria-hidden="true">
                      <span className="fill" style={{ width: `${top ? Math.max(1, (r.total / top) * 100) : 0}%` }} />
                    </span>
                    <span className="muted right">{r.count}</span>
                    <span className="mono right">{inr(r.total)}</span>
                  </div>
                ))}
              </div>
              {hidden > 0 && <p className="muted">And {hidden} more. Narrow the filters to see them.</p>}
              {breakdown && breakdown.rows.length === 0 && <div className="empty">Nothing to break down.</div>}
            </section>
          </>
        )
      )}

      <div className="card">
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Entry</th>
                <th>Category</th>
                <th>Tag</th>
                <th className="right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {page?.items.map((t) => (
                <tr key={t.id}>
                  <td>
                    {fmtDate(t.txn_ts)}
                    <div className="sub">{fmtTime(t.txn_ts)}</div>
                  </td>
                  <td>
                    {t.note_raw ?? <span className="muted">no note</span>}
                    {t.description && <div className="sub">{t.description}</div>}
                  </td>
                  <td>
                    {t.category}
                    {t.kind !== "expense" && <span className={`chip ${t.kind}`}>{t.kind}</span>}
                  </td>
                  <td>
                    {t.subcategory ? <span className="chip">{t.subcategory}</span> : <span className="muted">–</span>}
                    {t.merchant && <div className="sub">{t.merchant}</div>}
                  </td>
                  <td className="mono right">{inr(t.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {page && page.total === 0 && <div className="empty">No entries match these filters.</div>}
        <div className="row" style={{ alignItems: "center" }}>
          <span className="muted">
            {first}–{last} of {page?.total ?? 0}
          </span>
          <span style={{ display: "flex", gap: 8 }}>
            <button type="button" className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
              Previous
            </button>
            <button type="button" className="btn" disabled={!page || offset + LIMIT >= page.total} onClick={() => setOffset(offset + LIMIT)}>
              Next
            </button>
          </span>
        </div>
      </div>
    </>
  );
}

import { useEffect, useState } from "react";
import { api, TxnPage } from "../api";
import { fmtDate, fmtTime, inr } from "../format";

const LIMIT = 50;

export default function Transactions() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [kind, setKind] = useState("all");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState(""); // q, after a short pause
  const [offset, setOffset] = useState(0);
  const [categories, setCategories] = useState<string[]>([]);
  const [page, setPage] = useState<TxnPage | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .categoryMap()
      .then((rows) => setCategories([...new Set(rows.map((r) => r.category))].sort()))
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(q);
      setOffset(0);
    }, 300);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    let live = true;
    api
      .transactions({ from, to, kind, category, q: search, limit: LIMIT, offset })
      .then((p) => live && (setPage(p), setError("")))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [from, to, kind, category, search, offset]);

  const change = (set: (v: string) => void) => (e: { target: { value: string } }) => {
    set(e.target.value);
    setOffset(0);
  };

  const first = page && page.total ? offset + 1 : 0;
  const last = page ? Math.min(offset + LIMIT, page.total) : 0;

  return (
    <>
      <h1>Transactions</h1>

      <form className="filters" onSubmit={(e) => e.preventDefault()}>
        <label className="field">
          From
          <input type="date" value={from} onChange={change(setFrom)} />
        </label>
        <label className="field">
          To
          <input type="date" value={to} onChange={change(setTo)} />
        </label>
        <label className="field">
          Kind
          <select value={kind} onChange={change(setKind)}>
            <option value="all">All</option>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
            <option value="transfer">Transfer</option>
          </select>
        </label>
        <label className="field">
          Category
          <select value={category} onChange={change(setCategory)}>
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="field" style={{ flex: "1 1 200px" }}>
          Search
          <input type="search" placeholder="merchant, note, category" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </form>

      {error && <div className="banner error">{error}</div>}

      <div className="card">
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Entry</th>
                <th>Category</th>
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
                    {t.subcategory && <div className="sub">{t.subcategory}</div>}
                    {t.kind !== "expense" && <span className={`chip ${t.kind}`}>{t.kind}</span>}
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

import { useEffect, useState } from "react";
import { api, Summary, TxnPage } from "../api";
import DateRange from "../components/DateRange";
import { fmtDate, inr, monthBounds, monthInRange, monthLabel, Preset, presetRange, rangeLabel } from "../format";

type Detail = { categories: Summary; income: Summary; transfers: Summary; tagged: Summary; recent: TxnPage };

export default function Overview() {
  const [months, setMonths] = useState<Summary | null>(null);
  const [preset, setPreset] = useState<Preset | "custom">("custom");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [ready, setReady] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .summary({ group_by: "month" })
      .then((s) => {
        setMonths(s);
        if (s.rows.length) {
          const latest = monthBounds(s.rows[s.rows.length - 1].key); // start on the latest month with data
          setFrom(latest.from);
          setTo(latest.to);
        }
        setReady(true);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!ready) return;
    let live = true;
    Promise.all([
      api.summary({ group_by: "category", from, to, kind: "expense" }),
      api.summary({ group_by: "category", from, to, kind: "income" }),
      api.summary({ group_by: "category", from, to, kind: "transfer" }),
      api.summary({ group_by: "subcategory", from, to, kind: "expense" }),
      api.transactions({ from, to, limit: 10 }),
    ])
      .then(([categories, income, transfers, tagged, recent]) => {
        if (live) setDetail({ categories, income, transfers, tagged, recent });
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [ready, from, to]);

  if (error) return <div className="banner error">Could not load data: {error}</div>;
  if (!months) return <p className="muted">Loading…</p>;
  if (!months.rows.length)
    return (
      <>
        <h1>Overview</h1>
        <div className="card empty">
          Nothing here yet. <a href="#import">Import a Money Manager export</a> to get started.
        </div>
      </>
    );

  const pick = (id: Preset) => {
    const range = presetRange(id);
    setPreset(id);
    setFrom(range.from);
    setTo(range.to);
  };
  const pickMonth = (key: string) => {
    const b = monthBounds(key);
    setPreset("custom");
    setFrom(b.from);
    setTo(b.to);
  };

  const recentMonths = months.rows.slice(-12);
  const maxMonth = Math.max(...recentMonths.map((m) => m.total), 1);
  const cats = detail?.categories.rows ?? [];
  const maxCat = Math.max(...cats.map((c) => c.total), 1);
  const tagged = (detail?.tagged.rows ?? []).filter((r) => r.key !== "(none)");
  const maxTag = Math.max(...tagged.map((t) => t.total), 1);

  return (
    <>
      <div>
        <div className="muted">Showing</div>
        <h1>{rangeLabel(from, to)}</h1>
      </div>

      <DateRange
        preset={preset}
        from={from}
        to={to}
        onPreset={pick}
        onFrom={(v) => (setFrom(v), setPreset("custom"))}
        onTo={(v) => (setTo(v), setPreset("custom"))}
      />

      <section className="tiles" aria-label="Totals for this period">
        <Tile label="Spent" value={detail?.categories.total} note={`${detail?.categories.count ?? 0} entries`} />
        <Tile label="Income" value={detail?.income.total} note="salary, bonus, cashback" />
        <Tile label="Invested and EMIs" value={detail?.transfers.total} note="not counted as spend" />
      </section>

      <section className="card" aria-label="Spend by month">
        <h2>Spend by month</h2>
        <div className="months">
          {recentMonths.map((m) => (
            <button
              key={m.key}
              type="button"
              className="month-btn"
              aria-pressed={monthInRange(m.key, from, to)}
              aria-label={`${monthLabel(m.key)}: ${inr(m.total)}`}
              title={`${monthLabel(m.key)}: ${inr(m.total)}`}
              onClick={() => pickMonth(m.key)}
            >
              <span className="col" style={{ height: `${Math.max((m.total / maxMonth) * 100, 3)}%` }} />
              {monthLabel(m.key).split(" ")[0]}
            </button>
          ))}
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h2>By category</h2>
          {cats.length === 0 && <div className="muted">No spend in this period.</div>}
          {cats.slice(0, 10).map((c) => (
            <div className="bar-row" key={c.key}>
              <span title={c.key}>{c.key}</span>
              <div className="track" aria-hidden="true">
                <div className="fill" style={{ width: `${(c.total / maxCat) * 100}%` }} />
              </div>
              <span className="mono right">{inr(c.total)}</span>
            </div>
          ))}
        </div>

        {tagged.length > 0 && (
          <div className="card">
            <h2>Coffee, eating out, delivery</h2>
            {tagged.map((t) => (
              <div className="bar-row" key={t.key}>
                <span>
                  {t.key} <span className="muted">· {t.count}</span>
                </span>
                <div className="track" aria-hidden="true">
                  <div className="fill amber" style={{ width: `${(t.total / maxTag) * 100}%` }} />
                </div>
                <span className="mono right">{inr(t.total)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <div className="row">
          <h2>Latest entries in this period</h2>
          <a href="#transactions">View all</a>
        </div>
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
              {(detail?.recent.items ?? []).map((t) => (
                <tr key={t.id}>
                  <td className="muted">{fmtDate(t.txn_ts)}</td>
                  <td>{t.note_raw ?? <span className="muted">no note</span>}</td>
                  <td>
                    {t.category}
                    {t.kind !== "expense" && <span className={`chip ${t.kind}`}> {t.kind}</span>}
                  </td>
                  <td className="mono right">{inr(t.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function Tile({ label, value, note }: { label: string; value: number | undefined; note: string }) {
  return (
    <div className="card">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value === undefined ? "…" : inr(value)}</div>
      <div className="tile-note">{note}</div>
    </div>
  );
}

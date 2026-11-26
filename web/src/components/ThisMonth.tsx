import { useEffect, useState } from "react";
import { insights, MonthInsight } from "../api";
import { fmtDay, inr as inrExact, monthLabel, num } from "../format";
const inr = (n: number) => inrExact(Math.round(n));
import { maskText } from "../privacy";

const KEY = "munim.dismissed-flags";
const readDismissed = (): string[] => {
  try {
    return JSON.parse(window.localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
};

/** Pace, what is still to come, what changed and entries worth a look, for the month of the latest entry. */
export default function ThisMonth() {
  const [data, setData] = useState<MonthInsight | null>(null);
  const [error, setError] = useState("");
  const [dismissed, setDismissed] = useState<string[]>(readDismissed);

  useEffect(() => {
    insights.month().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <div className="banner error">Could not work out this month: {error}</div>;
  if (!data) return <p className="muted">Working out this month…</p>;

  const dismiss = (key: string) => {
    const next = [...dismissed, key];
    setDismissed(next);
    try {
      window.localStorage.setItem(KEY, JSON.stringify(next.slice(-200)));
    } catch {
      /* kept for this visit only */
    }
  };
  const flags = data.flags.filter((f) => !dismissed.includes(f.key)).slice(0, 3);
  const over = data.usual_to_date === null ? null : data.spent - data.usual_to_date;
  const scale = Math.max(data.projected ?? 0, data.usual_month ?? 0, data.spent, 1);
  const pct = (v: number) => `${Math.min((v / scale) * 100, 100)}%`;

  return (
    <>
      <div className="muted">
        {monthLabel(data.month)} · as of {fmtDay(data.as_of)}, day {data.day} of {data.days_in_month}
      </div>
      <section className="card pace" aria-label="Spending pace">
        <div className="tile-label">Spent so far · pace</div>
        <div className="tile-value">
          {inr(data.spent)}{" "}
          {over !== null && Math.abs(over) >= 1 && (
            <span className="pace-delta" style={{ color: over > 0 ? "var(--bad)" : "var(--good)" }}>
              {over > 0 ? "▲" : "▼"} {inr(Math.abs(over))} {over > 0 ? "over" : "under"} usual
            </span>
          )}
        </div>
        {data.usual_to_date !== null ? (
          <>
            <div className="pace-bar" aria-hidden="true">
              <div className="pace-fill" style={{ width: pct(data.spent) }} />
              <div className="pace-usual" style={{ left: pct(data.usual_to_date) }} />
              {data.projected !== null && <div className="pace-proj" style={{ left: pct(data.projected) }} />}
            </div>
            <div className="pace-legend">
              <span>
                <span className="key usual" /> usual by day {data.day}: <b className="mono">{inr(data.usual_to_date)}</b>
              </span>
              <span>
                <span className="key proj" /> heading for <b className="mono">{inr(data.projected ?? 0)}</b>{" "}
                <span className="muted">(usual month {inr(data.usual_month ?? 0)})</span>
              </span>
            </div>
            <div className="tile-note">compared with the same days of the last {num(data.history_months)} months</div>
          </>
        ) : (
          <div className="tile-note">Pace needs at least one earlier month of entries.</div>
        )}
        {data.still_to_come.items.length > 0 && (
          <a className="committed" href="#transactions/recurring">
            {inr(data.still_to_come.total)} of recurring charges still to come this month ({num(data.still_to_come.items.length)}):{" "}
            {data.still_to_come.items.map((r) => r.merchant).join(", ")} →
          </a>
        )}
      </section>

      <section className="grid">
        <div className="card">
          <h2>What changed</h2>
          {data.movers.length === 0 ? (
            <div className="muted">Nothing moved by more than ₹1,000 against your usual for these days.</div>
          ) : (
            <>
              {data.movers.map((m) => (
                <div className="mover" key={m.category}>
                  <span>{m.category}</span>
                  <span className="mono right" style={{ color: m.delta > 0 ? "var(--bad)" : "var(--good)" }}>
                    {m.delta > 0 ? "+" : "−"}
                    {inr(Math.abs(m.delta))}
                  </span>
                  <span className="muted">{m.merchants.join(", ") || "spread across many entries"}</span>
                </div>
              ))}
              <div className="tile-note">
                vs your average for the same {num(data.day)} days. Everything else moved by less than ₹1,000.
              </div>
            </>
          )}
        </div>
        <div className="card">
          <h2>Worth a look{flags.length ? ` (${flags.length})` : ""}</h2>
          {flags.length === 0 && <div className="muted">Nothing odd this month.</div>}
          {flags.map((f) => (
            <div className="flag" key={f.key}>
              <span className="flag-mark" aria-hidden="true">!</span>
              <div>
                <div>{f.title}</div>
                <div className="muted">{maskText(f.detail)}</div>
              </div>
              <button type="button" className="btn" onClick={() => dismiss(f.key)}>
                Dismiss
              </button>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

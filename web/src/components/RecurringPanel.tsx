import { useEffect, useState } from "react";
import { insights, RecurringList } from "../api";
import { fmtDay, inr, num } from "../format";

/** Charges that repeat. Found from all entries, so the filters above don't apply. */
export default function RecurringPanel() {
  const [data, setData] = useState<RecurringList | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    insights.recurring().then(setData).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <div className="banner error">Could not find recurring charges: {error}</div>;
  if (!data) return <p className="muted">Looking for recurring charges…</p>;
  if (!data.items.length) return <div className="empty">No charge repeats steadily enough yet.</div>;

  const live = data.items.filter((r) => !r.stopped);
  const soon = (d: string | null) => !!d && d > data.as_of && d.slice(0, 7) === data.as_of.slice(0, 7);
  return (
    <>
      <section className="tiles" style={{ margin: "12px 0" }}>
        <div className="card">
          <div className="tile-label">Each month</div>
          <div className="tile-value">{inr(data.monthly_total)}</div>
          <div className="tile-note">{num(live.length)} regular charges, yearly ones spread out</div>
        </div>
        <div className="card">
          <div className="tile-label">Still to come this month</div>
          <div className="tile-value" style={{ color: "var(--accent)" }}>{inr(data.still_to_come)}</div>
          <div className="tile-note">{num(data.still_to_come_count)} {data.still_to_come_count === 1 ? "charge" : "charges"} after {fmtDay(data.as_of)}</div>
        </div>
        <div className="card">
          <div className="tile-label">Changed</div>
          <div className="tile-value" style={data.changed ? { color: "var(--bad)" } : undefined}>{num(data.changed)}</div>
          <div className="tile-note">price changes and charges that stopped</div>
        </div>
      </section>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Merchant</th>
              <th>Category</th>
              <th className="right">Usual</th>
              <th>Every</th>
              <th>Last</th>
              <th>Next expected</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={`${r.kind}:${r.merchant}`}>
                <td>{r.merchant}</td>
                <td className="muted">
                  {r.category}
                  {r.kind === "transfer" && <span className="chip transfer"> transfer</span>}
                </td>
                <td className="mono right">{inr(r.usual)}</td>
                <td className="muted">{r.every}</td>
                <td className="muted">{fmtDay(r.last)}</td>
                <td style={soon(r.next) ? { color: "var(--accent)" } : undefined}>
                  {r.next ? fmtDay(r.next) : "–"}
                  {r.next && r.next < data.as_of && <div className="sub">not seen yet</div>}
                </td>
                <td style={{ color: "var(--bad)" }}>
                  {r.stopped ? `stopped? nothing since ${fmtDay(r.last)}` : r.previous_amount !== null ? `was ${inr(r.previous_amount)}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tile-note">
        Found from all your entries, so the filters above don't apply: the same merchant at about the same amount, at a steady gap, at least 3
        times. Amber dates are counted in Overview's "still to come".
      </p>
    </>
  );
}

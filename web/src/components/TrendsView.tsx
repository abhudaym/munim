import { useEffect, useState } from "react";
import { insights, Trends } from "../api";
import { monthLabel, num } from "../format";
import { isHidden } from "../privacy";
import { MultiLine } from "./Chart";

const pct = (v: number | null, sign = false) =>
  v === null ? "–" : isHidden() ? "****" : `${sign && v > 0 ? "+" : ""}${Math.round(v * 100)}%`;
const SHADES = ["var(--raised)", "#4a3a12", "#8a6410", "#c98a00", "#ffb000"];

/** Slow trends over the last 12 full months. They do not follow the date picker. */
export default function TrendsView() {
  const [data, setData] = useState<Trends | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    insights.trends().then(setData).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <div className="banner error">Could not load trends: {error}</div>;
  if (!data) return <p className="muted">Working out trends…</p>;
  if (!data.months.length) return <div className="card empty">Trends start once there is a full month of entries.</div>;

  const pts = data.savings.filter((s) => s.rate !== null);
  const last = pts[pts.length - 1];
  const top = Math.max(...data.grid.flat(), 1);
  const shade = (v: number) => SHADES[v <= 0 ? 0 : Math.min(4, Math.ceil((v / top) * 4))];
  const maxGrowth = Math.max(...data.growth.map((g) => Math.abs(g.pct ?? 0)), 0.01);
  const income = data.growth[0]?.pct ?? null;

  return (
    <>
      <div className="muted">
        The last {num(data.months.length)} full months, {monthLabel(data.months[0])} to {monthLabel(data.months[data.months.length - 1])}. These
        don't follow the date picker.
      </div>
      <section className="grid">
        <div className="card">
          <h2>Savings rate</h2>
          {last ? (
            <div className="tile-value">
              {pct(last.rate)}{" "}
              <span className="muted" style={{ fontSize: 13 }}>
                saved in {monthLabel(last.month)} · average {pct(data.savings_avg)}
              </span>
            </div>
          ) : (
            <div className="muted">No income entered in these months.</div>
          )}
          {pts.length > 1 && (
            <MultiLine
              plot={{
                labels: pts.map((p) => p.month),
                column: "rate_pct",
                series: [{ name: "Savings rate %", values: pts.map((p) => Math.round((p.rate ?? 0) * 1000) / 10) }],
              }}
            />
          )}
          <div className="tile-note">(income − spend − EMIs) ÷ income. Investments count as saved.</div>
        </div>

        <div className="card">
          <h2>Lifestyle creep</h2>
          {data.growth.length === 0 ? (
            <div className="muted">This needs at least 6 full months of entries, to compare the latest 3 with the 3 before.</div>
          ) : (
            <>
              <div className="tile-note">
                Monthly average, last {num(data.recent_months)} months vs the {num(data.before_months)} before.
              </div>
              {data.growth.map((g, i) => {
                const v = g.pct ?? 0;
                const w = (Math.abs(v) / maxGrowth) * 50;
                return (
                  <div className={`creep${i === 0 ? " ref" : ""}`} key={g.category}>
                    <span>{g.category}</span>
                    <div className="creep-track" aria-hidden="true">
                      <div className="creep-mid" />
                      {g.pct !== null && (
                        <div
                          className={`creep-bar${g.faster_than_income ? " hot" : ""}${i === 0 ? " inc" : ""}`}
                          style={{ left: v >= 0 ? "50%" : `${50 - w}%`, width: `${w}%` }}
                        />
                      )}
                    </div>
                    <span className="mono right" style={{ color: g.faster_than_income ? "var(--bad)" : v < 0 && i > 0 ? "var(--good)" : undefined }}>
                      {g.pct === null ? "new" : pct(g.pct, true)}
                    </span>
                  </div>
                );
              })}
              <div className="tile-note">Amber: growing faster than your income ({pct(income, true)}).</div>
            </>
          )}
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h2>When you spend</h2>
          <div className="heat" role="table" aria-label="Spend by weekday and time of day">
            <span />
            {data.slots.map((s) => (
              <span key={s} className="muted heat-head">
                {s}
              </span>
            ))}
            {data.days.map((d, i) => (
              <div key={d} style={{ display: "contents" }}>
                <span className="muted">{d}</span>
                {data.grid[i].map((v, j) => (
                  <div key={j} className="heat-cell" style={{ background: shade(v) }} title={`${d} ${data.slots[j]}`} />
                ))}
              </div>
            ))}
          </div>
          <div className="heat-key muted">
            less {SHADES.map((s) => <span key={s} style={{ background: s }} />)} more
          </div>
          {data.weekend_share !== null && (
            <p>
              <b className="mono">{pct(data.weekend_share)}</b> <span className="muted">of spend is on weekends. Your busiest slot is {data.top_slot}.</span>
            </p>
          )}
          <div className="tile-note">Times are when the entry was made in Money Manager, which is usually but not always when you paid.</div>
        </div>
      </section>
    </>
  );
}

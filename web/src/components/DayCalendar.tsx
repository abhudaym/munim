import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Daily, DaySpend, insights } from "../api";
import { fmtDay, inr, num } from "../format";

const CELL = 14;
const GAP = 3;
const LEVELS = ["var(--raised)", "#4a3a12", "#8a6410", "#c98a00", "#ffb000"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const parse = (s: string) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const between = (a: Date, b: Date) => Math.round((b.getTime() - a.getTime()) / 86400000);
const weekday = (d: Date) => (d.getDay() + 6) % 7; // Monday first
const money = (n: number) => inr(Math.round(n));
const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** A year of days, like a contribution graph: one square per day, brighter for more spend. */
export default function DayCalendar() {
  const [data, setData] = useState<Daily | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    insights.daily().then(setData).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <div className="banner error">Could not load the daily calendar: {error}</div>;
  if (!data) return <p className="muted">Working out the calendar…</p>;
  if (!data.tracked_from) return <div className="card empty">The daily calendar starts once there are entries.</div>;
  return <Calendar data={data} />;
}

function Calendar({ data }: { data: Daily }) {
  const start = parse(data.start);
  const end = parse(data.end);
  const gridStart = addDays(start, -weekday(start)); // the Monday on or before the first day
  const nCells = between(gridStart, end) + 1;
  const cols = Math.ceil(nCells / 7);
  const firstIdx = between(gridStart, start);

  const byDay = useMemo(() => new Map<string, DaySpend>(data.days.map((d) => [d.day, d])), [data]);
  // Shading is by rank among days with spend, so one big trip day does not wash out every other day.
  const cuts = useMemo(() => {
    const s = data.days.map((d) => d.total).sort((a, b) => a - b);
    if (!s.length) return [0, 0, 0];
    const q = (p: number) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
    return [q(0.25), q(0.5), q(0.75)];
  }, [data]);
  const level = (v: number) => (v <= 0 ? 0 : v <= cuts[0] ? 1 : v <= cuts[1] ? 2 : v <= cuts[2] ? 3 : 4);

  const [active, setActive] = useState<number | null>(null);
  const idx = active ?? nCells - 1;
  const scroller = useRef<HTMLDivElement>(null);
  const grid = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollLeft = el.scrollWidth; // the latest weeks are on the right; start there on a phone
  }, []);

  const onKey = (e: KeyboardEvent) => {
    const step = ({ ArrowDown: 1, ArrowUp: -1, ArrowRight: 7, ArrowLeft: -7 } as Record<string, number>)[e.key];
    if (!step) return;
    e.preventDefault();
    const next = Math.max(firstIdx, Math.min(nCells - 1, idx + step));
    setActive(next);
    requestAnimationFrame(() =>
      grid.current?.querySelector(`[data-i="${next}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" }),
    );
  };

  // A label over the column that holds the 1st of each month, with the year.
  const cand: { col: number; month: number; year: number }[] = [];
  for (let c = 0; c < cols; c++) {
    for (let r = 0; r < 7; r++) {
      const i = c * 7 + r;
      if (i < firstIdx || i >= nCells) continue;
      const d = addDays(gridStart, i);
      if (d.getDate() === 1) {
        cand.push({ col: c, month: d.getMonth(), year: d.getFullYear() });
        break;
      }
    }
  }
  if (!cand.length || cand[0].col >= 4) cand.unshift({ col: 0, month: start.getMonth(), year: start.getFullYear() });
  const labels = cand.filter((l) => cols - l.col >= 3); // a label needs about three columns of room

  const cur = addDays(gridStart, idx);
  const curKey = iso(cur);
  const rec = byDay.get(curKey);
  const curUnknown = curKey < data.tracked_from!;

  return (
    <>
      <section className="card" aria-label="Daily spend">
        <div className="row" style={{ alignItems: "center" }}>
          <h2>Day by day</h2>
          <span className="muted">last 12 months to {fmtDay(data.end)}</span>
        </div>
        <div className="readout" aria-live="polite">
          {WEEKDAYS[weekday(cur)]} {fmtDay(curKey)} ·{" "}
          {curUnknown ? (
            <span className="muted">before your first entry</span>
          ) : rec ? (
            <>
              <b className="mono">{money(rec.total)}</b>{" "}
              <span className="muted">
                {num(rec.count)} {plural(rec.count, "entry", "entries")}
              </span>
            </>
          ) : (
            <span className="muted">no spend</span>
          )}
        </div>
        <div className="daycal-scroll" ref={scroller}>
          <div
            className="daycal"
            ref={grid}
            tabIndex={0}
            role="group"
            aria-label="Daily spend calendar. Use the arrow keys to move between days."
            onKeyDown={onKey}
            style={{ gridTemplateColumns: `30px repeat(${cols}, ${CELL}px)`, gridTemplateRows: `16px repeat(7, ${CELL}px)`, gap: GAP }}
          >
            {labels.map((l) => (
              <span key={`${l.year}-${l.month}`} className="daycal-label month" style={{ gridRow: 1, gridColumn: l.col + 2 }}>
                {MONTHS[l.month]} '{String(l.year).slice(2)}
              </span>
            ))}
            {[0, 2, 4].map((r) => (
              <span key={r} className="daycal-label" style={{ gridColumn: 1, gridRow: r + 2 }}>
                {WEEKDAYS[r]}
              </span>
            ))}
            {Array.from({ length: nCells - firstIdx }, (_, k) => {
              const i = firstIdx + k;
              const key = iso(addDays(gridStart, i));
              const unknown = key < data.tracked_from!;
              return (
                <div
                  key={key}
                  data-i={i}
                  aria-hidden="true"
                  className={`daycal-cell${unknown ? " unknown" : ""}${i === idx ? " on" : ""}`}
                  style={{
                    gridColumn: Math.floor(i / 7) + 2,
                    gridRow: (i % 7) + 2,
                    background: unknown ? undefined : LEVELS[level(byDay.get(key)?.total ?? 0)],
                  }}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => setActive(i)}
                />
              );
            })}
          </div>
        </div>
        <div className="heat-key muted">
          less {LEVELS.map((s) => <span key={s} style={{ background: s }} />)} more
        </div>
        <div className="tile-note">
          Shading ranks your spending days, so one big trip day doesn't wash out the rest. A day with no entry counts as no spend. SIPs and EMIs
          aren't spend. Dashed squares are before your first entry.
        </div>
      </section>

      <section className="tiles" style={{ margin: "16px 0" }}>
        <div className="card">
          <div className="tile-label">Spent</div>
          <div className="tile-value">{money(data.total)}</div>
          <div className="tile-note">
            about {money(data.total / Math.max(data.tracked_days, 1))} a day over {num(data.tracked_days)} days
          </div>
        </div>
        <div className="card">
          <div className="tile-label">No-spend days</div>
          <div className="tile-value">{num(data.no_spend_days)}</div>
          <div className="tile-note">of {num(data.tracked_days)} days since {fmtDay(data.tracked_from!)}</div>
        </div>
        <div className="card">
          <div className="tile-label">Longest no-spend run</div>
          <div className="tile-value">
            {num(data.longest_no_spend.days)} {plural(data.longest_no_spend.days, "day", "days")}
          </div>
          <div className="tile-note">
            {data.longest_no_spend.start ? `${fmtDay(data.longest_no_spend.start)} to ${fmtDay(data.longest_no_spend.end!)} · ` : ""}
            now {num(data.current_no_spend.days)}
          </div>
        </div>
        <div className="card">
          <div className="tile-label">Biggest day</div>
          <div className="tile-value">{data.biggest ? money(data.biggest.total) : "–"}</div>
          <div className="tile-note">
            {data.biggest ? `${fmtDay(data.biggest.day)} · ${num(data.biggest.count)} ${plural(data.biggest.count, "entry", "entries")}` : ""}
          </div>
        </div>
      </section>
    </>
  );
}

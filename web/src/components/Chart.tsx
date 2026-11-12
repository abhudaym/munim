import { useState } from "react";
import { inr, monthLabel } from "../format";

export type ChartKind = "number" | "bars" | "line" | "table";
export type Cell = string | number | null;
export type ChartData = {
  columns: string[];
  rows: Cell[][];
  chart: string;
  value_col: number | null;
  time: boolean;
  plot?: Plot | null;
};
export type Plot = { labels: string[]; column: string; series: { name: string; values: number[] }[] };

const MONEY = /(amount|total|spent|spend|sum|avg|average|income|expense|max|min|cost)/i;
const MONTH = /^\d{4}-\d{2}$/;

export const isMoney = (column: string) => MONEY.test(column);
export const fmtValue = (column: string, v: number) => (isMoney(column) ? inr(v) : v.toLocaleString("en-IN"));
const fmtLabel = (v: Cell) => (v === null ? "none" : typeof v === "string" && MONTH.test(v) ? monthLabel(v) : String(v));

const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
/** Axis label for a time bucket: month and 2-digit year, so the year is always readable. */
const axisLabel = (v: Cell) => {
  if (typeof v !== "string") return String(v ?? "");
  if (MONTH.test(v)) return `${MON[Number(v.slice(5, 7)) - 1]} '${v.slice(2, 4)}`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return `${Number(v.slice(8))} ${MON[Number(v.slice(5, 7)) - 1]} '${v.slice(2, 4)}`;
  return v;
};

/** A round upper bound and evenly spaced ticks, so the y axis reads in clean steps. */
function niceScale(top: number) {
  const target = Math.max(top, 1) / 4;
  const mag = 10 ** Math.floor(Math.log10(target));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((c) => c >= target) ?? 10 * mag;
  const max = step * Math.ceil(Math.max(top, 1) / step);
  return { max, ticks: Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step) };
}

/** Compact amounts for axis ticks: 12.5k, 1.2L (lakh), 3Cr. */
function fmtTick(column: string, v: number) {
  const trim = (n: number) => String(Math.round(n * 10) / 10);
  const a = Math.abs(v);
  const body = a >= 1e7 ? `${trim(v / 1e7)}Cr` : a >= 1e5 ? `${trim(v / 1e5)}L` : a >= 1e3 ? `${trim(v / 1e3)}k` : String(v);
  return isMoney(column) ? `₹${body}` : body;
}

function YAxis({ column, ticks, max }: { column: string; ticks: number[]; max: number }) {
  return (
    <div className="yaxis" aria-hidden="true">
      {ticks.map((t) => (
        <span key={t} style={{ bottom: `${(t / max) * 100}%` }}>{fmtTick(column, t)}</span>
      ))}
    </div>
  );
}

function Grid({ ticks, max }: { ticks: number[]; max: number }) {
  return (
    <>
      {ticks.map((t) => (t > 0 ? <span key={t} className="gridline" style={{ bottom: `${(t / max) * 100}%` }} aria-hidden="true" /> : null))}
    </>
  );
}

function cell(column: string, value: Cell) {
  if (value === null) return <span className="muted">–</span>;
  if (typeof value === "number") return fmtValue(column, value);
  return fmtLabel(value);
}

export function ResultTable({ columns, rows }: { columns: string[]; rows: Cell[][] }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c, j) => (
              <th key={c} className={typeof rows[0]?.[j] === "number" ? "right" : ""}>{c.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j} className={typeof v === "number" ? "mono right" : ""}>{cell(columns[j], v)}</td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={columns.length || 1} className="muted">No matching entries.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Time series: columns or a line, with one readout that follows hover and keyboard focus. */
function TimeChart({ points, column, line }: { points: { label: Cell; value: number }[]; column: string; line: boolean }) {
  const [active, setActive] = useState(points.length - 1);
  const { max: top, ticks } = niceScale(Math.max(...points.map((p) => p.value), 1));
  const at = points[Math.min(active, points.length - 1)];
  const step = Math.ceil(points.length / 7); // thin the axis labels when there are many
  const x = (i: number) => ((i + 0.5) / points.length) * 100;
  const y = (v: number) => 100 - (v / top) * 100;

  return (
    <div className="tchart">
      <div className="readout" aria-live="polite">
        <span className="muted">{fmtLabel(at.label)}</span> <strong>{fmtValue(column, at.value)}</strong>
      </div>
      <div className="chartgrid">
      <YAxis column={column} ticks={ticks} max={top} />
      <div className="plot">
        <Grid ticks={ticks} max={top} />
        {line && (
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <polyline points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")} fill="none" vectorEffect="non-scaling-stroke" />
          </svg>
        )}
        {points.map((p, i) => (
          <button
            type="button"
            key={i}
            className={`slot ${i === active ? "on" : ""}`}
            aria-label={`${fmtLabel(p.label)}: ${fmtValue(column, p.value)}`}
            onMouseEnter={() => setActive(i)}
            onFocus={() => setActive(i)}
          >
            {line ? (
              <span className="dot" style={{ bottom: `${(p.value / top) * 100}%` }} />
            ) : (
              <span className="colbar" style={{ height: `${Math.max(1, (p.value / top) * 100)}%` }} />
            )}
          </button>
        ))}
      </div>
      <div className="xaxis" aria-hidden="true">
        {points.map((p, i) => (
          <span key={i}>{i % step === 0 ? axisLabel(p.label) : ""}</span>
        ))}
      </div>
      </div>
    </div>
  );
}

/** Several lines over time, one colour per series in fixed order, one shared y-scale. */
function MultiLine({ plot }: { plot: Plot }) {
  const n = plot.labels.length;
  const [active, setActive] = useState(n - 1);
  const { max: top, ticks } = niceScale(Math.max(...plot.series.flatMap((s) => s.values), 1));
  const i = Math.min(active, n - 1);
  const step = Math.ceil(n / 7);
  const x = (k: number) => ((k + 0.5) / n) * 100;
  const y = (v: number) => 100 - (v / top) * 100;

  return (
    <div className="tchart">
      <div className="legend">
        {plot.series.map((s, k) => (
          <span key={s.name}>
            <i className="swatch" style={{ background: `var(--s${k + 1})` }} /> {s.name}
          </span>
        ))}
      </div>
      <div className="readout" aria-live="polite">
        <span className="muted">{fmtLabel(plot.labels[i])}</span>{" "}
        {plot.series.map((s) => (
          <span key={s.name} className="rv">
            {s.name} <strong>{fmtValue(plot.column, s.values[i])}</strong>
          </span>
        ))}
      </div>
      <div className="chartgrid">
      <YAxis column={plot.column} ticks={ticks} max={top} />
      <div className="plot">
        <Grid ticks={ticks} max={top} />
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {plot.series.map((s, k) => (
            <polyline
              key={s.name}
              className="ml"
              style={{ stroke: `var(--s${k + 1})` }}
              points={s.values.map((v, j) => `${x(j)},${y(v)}`).join(" ")}
              fill="none"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
        {plot.labels.map((label, j) => (
          <button
            type="button"
            key={j}
            className={`slot ${j === i ? "on" : ""}`}
            aria-label={`${fmtLabel(label)}: ${plot.series.map((s) => `${s.name} ${fmtValue(plot.column, s.values[j])}`).join(", ")}`}
            onMouseEnter={() => setActive(j)}
            onFocus={() => setActive(j)}
          >
            {plot.series.map((s, k) => (
              <span key={s.name} className="dot" style={{ bottom: `${(s.values[j] / top) * 100}%`, background: `var(--s${k + 1})` }} />
            ))}
          </button>
        ))}
      </div>
      <div className="xaxis" aria-hidden="true">
        {plot.labels.map((label, j) => (
          <span key={j}>{j % step === 0 ? axisLabel(label) : ""}</span>
        ))}
      </div>
      </div>
    </div>
  );
}

export default function Chart({ data, kind }: { data: ChartData; kind?: string }) {
  const chart = kind ?? data.chart;
  if (data.plot && chart === "line" && data.rows.length > 0) return <MultiLine plot={data.plot} />;
  const v = data.value_col;
  if (data.rows.length === 0 || chart === "table" || v === null) return <ResultTable columns={data.columns} rows={data.rows} />;

  const column = data.columns[v];
  if (chart === "number") {
    const value = data.rows[0][v];
    return <div className="headline">{typeof value === "number" ? fmtValue(column, value) : "–"}</div>;
  }

  const points = data.rows.map((r) => ({ label: r[0], value: typeof r[v] === "number" ? (r[v] as number) : 0 }));
  if (data.time) return <TimeChart points={points} column={column} line={chart === "line"} />;

  const top = Math.max(...points.map((p) => p.value), 1);
  return (
    <div className="bars">
      {points.map((p, i) => (
        <div className="bar-row three" key={i}>
          <span className={p.label === null ? "muted" : ""}>{fmtLabel(p.label)}</span>
          <span className="track" aria-hidden="true">
            <span className="fill" style={{ width: `${Math.max(1, (p.value / top) * 100)}%` }} />
          </span>
          <span className="mono right">{fmtValue(column, p.value)}</span>
        </div>
      ))}
    </div>
  );
}

const LABELS: Record<string, string> = { number: "Number", bars: "Bars", line: "Line", table: "Table" };

export function ChartPicker({ options, value, onChange, label }: { options: string[]; value: string; onChange: (k: string) => void; label: string }) {
  if (options.length < 2) return null;
  return (
    <div className="tabs" role="group" aria-label={label}>
      {options.map((k) => (
        <button type="button" key={k} aria-pressed={value === k} onClick={() => onChange(k)}>
          {LABELS[k] ?? k}
        </button>
      ))}
    </div>
  );
}

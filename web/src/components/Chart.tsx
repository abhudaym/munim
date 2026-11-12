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
const shortLabel = (v: Cell) => {
  if (typeof v !== "string") return String(v ?? "");
  if (MONTH.test(v)) return monthLabel(v).split(" ")[0];
  return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v.slice(8) : v;
};

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
  const top = Math.max(...points.map((p) => p.value), 1);
  const at = points[Math.min(active, points.length - 1)];
  const step = Math.ceil(points.length / 8); // thin the axis labels when there are many
  const x = (i: number) => ((i + 0.5) / points.length) * 100;
  const y = (v: number) => 100 - (v / top) * 100;

  return (
    <div className="tchart">
      <div className="readout" aria-live="polite">
        <span className="muted">{fmtLabel(at.label)}</span> <strong>{fmtValue(column, at.value)}</strong>
      </div>
      <div className="plot">
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
          <span key={i}>{i % step === 0 || i === points.length - 1 ? shortLabel(p.label) : ""}</span>
        ))}
      </div>
    </div>
  );
}

/** Several lines over time, one colour per series in fixed order, one shared y-scale. */
function MultiLine({ plot }: { plot: Plot }) {
  const n = plot.labels.length;
  const [active, setActive] = useState(n - 1);
  const top = Math.max(...plot.series.flatMap((s) => s.values), 1);
  const i = Math.min(active, n - 1);
  const step = Math.ceil(n / 8);
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
      <div className="plot">
        <span className="ymax muted" aria-hidden="true">{fmtValue(plot.column, top)}</span>
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
          <span key={j}>{j % step === 0 || j === n - 1 ? shortLabel(label) : ""}</span>
        ))}
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

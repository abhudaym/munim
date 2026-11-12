const inr0 = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

/** Whole rupees for totals; paise only when the amount has them. */
export const inr = (n: number) => (Number.isInteger(n) ? inr0.format(n) : inr2.format(n));

const day = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const time = new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });

// The API sends naive local timestamps; `new Date(str)` reads those as local time.
export const fmtDate = (iso: string) => day.format(new Date(iso));
export const fmtTime = (iso: string) => time.format(new Date(iso));

export const monthLabel = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString("en-IN", { month: "short", year: "numeric" });
};

/** First and last day of 'YYYY-MM' as 'YYYY-MM-DD' strings. */
export const monthBounds = (ym: string) => {
  const [y, m] = ym.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return { from: `${ym}-01`, to: `${ym}-${String(last).padStart(2, "0")}` };
};

export const kindLabel: Record<string, string> = {
  expense: "Expense",
  income: "Income",
  transfer: "Transfer",
};

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export type Preset = "month" | "last_month" | "3m" | "year" | "all";
export const PRESETS: { id: Preset; label: string }[] = [
  { id: "month", label: "This month" },
  { id: "last_month", label: "Last month" },
  { id: "3m", label: "Last 3 months" },
  { id: "year", label: "This year" },
  { id: "all", label: "All time" },
];

/** Date range for a preset, as 'YYYY-MM-DD' strings in local time. */
export const presetRange = (preset: Preset, today = new Date()) => {
  const y = today.getFullYear();
  const m = today.getMonth();
  switch (preset) {
    case "month":
      return { from: iso(new Date(y, m, 1)), to: iso(today) };
    case "last_month":
      return { from: iso(new Date(y, m - 1, 1)), to: iso(new Date(y, m, 0)) };
    case "3m": {
      // same day three months back, clamped to that month's last day
      const last = new Date(y, m - 2, 0).getDate();
      return { from: iso(new Date(y, m - 3, Math.min(today.getDate(), last))), to: iso(today) };
    }
    case "year":
      return { from: iso(new Date(y, 0, 1)), to: iso(today) };
    default:
      return { from: "", to: "" };
  }
};

const ymd = (s: string) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d); // local time; 'YYYY-MM-DD' alone would be read as UTC
};
export const fmtDay = (s: string) => day.format(ymd(s));

/** Heading for a date range: a month name when it is exactly one month, else the dates. */
export const rangeLabel = (from: string, to: string) => {
  if (!from && !to) return "All time";
  if (from && to && from.slice(0, 7) === to.slice(0, 7)) {
    const b = monthBounds(from.slice(0, 7));
    if (b.from === from && b.to === to) return monthLabel(from.slice(0, 7));
  }
  if (from && to) return `${fmtDay(from)} – ${fmtDay(to)}`;
  return from ? `From ${fmtDay(from)}` : `Up to ${fmtDay(to)}`;
};

/** Does 'YYYY-MM' overlap the range? An empty end is open. */
export const monthInRange = (ym: string, from: string, to: string) => {
  const b = monthBounds(ym);
  return (!from || b.to >= from) && (!to || b.from <= to);
};

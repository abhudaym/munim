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

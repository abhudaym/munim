import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bill, Card, cards } from "../api";
import Chart from "../components/Chart";
import { fmtDate, inr } from "../format";

const day = (iso: string) => fmtDate(`${iso}T00:00:00`);
const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ordinal = (n: number) => {
  const r = n % 100;
  if (r >= 11 && r <= 13) return `${n}th`;
  return `${n}${["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
};
const inDays = (n: number) => (n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`);
const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(/,/g, "")));

function statusText(b: Bill) {
  if (b.status === "paid") return `paid ${b.paid_on ? day(b.paid_on) : ""}`;
  if (b.days_to_due === null) return "unpaid, no due date";
  if (b.days_to_due < 0) return `overdue by ${-b.days_to_due} ${b.days_to_due === -1 ? "day" : "days"}`;
  return `due ${inDays(b.days_to_due)}`;
}
const statusColor = (b: Bill) => (b.status === "overdue" ? "var(--bad)" : b.status === "paid" ? "var(--good)" : "var(--accent)");

export default function Cards() {
  const [list, setList] = useState<Card[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    cards.list().then(setList).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setError("");
    try {
      await fn();
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!list) return error ? <div className="banner error">Could not load: {error}</div> : <p className="muted">Loading…</p>;

  const live = list.filter((c) => !c.archived);
  const archived = list.filter((c) => c.archived);
  const unpaid = live.reduce((a, c) => a + c.unpaid_total, 0);
  const dueSoon = live.filter((c) => c.next_due).sort((a, b) => a.next_due!.localeCompare(b.next_due!))[0];
  const billSoon = [...live].sort((a, b) => a.days_to_statement - b.days_to_statement)[0];
  const todayIso = iso(new Date());

  return (
    <>
      <h1>
        Cards <span className="muted">/ bills you type in. Nothing here touches your expenses.</span>
      </h1>
      {error && <div className="banner error">{error}</div>}

      <section className="tiles" aria-label="Card totals">
        <div className="card">
          <div className="tile-label">Unpaid bills</div>
          <div className="tile-value" style={unpaid > 0 ? { color: "var(--accent)" } : undefined}>{inr(unpaid)}</div>
          <div className="tile-note">{live.reduce((a, c) => a + c.unpaid_count, 0)} bills not marked paid</div>
        </div>
        <div className="card">
          <div className="tile-label">Next due date</div>
          <div className="tile-value">{dueSoon?.next_due ? day(dueSoon.next_due) : "–"}</div>
          <div className="tile-note">{dueSoon ? dueSoon.name : "no unpaid bill with a due date"}</div>
        </div>
        <div className="card">
          <div className="tile-label">Next bill generated</div>
          <div className="tile-value">{billSoon ? day(billSoon.next_statement) : "–"}</div>
          <div className="tile-note">{billSoon ? `${billSoon.name}, ${inDays(billSoon.days_to_statement)}` : "add a card"}</div>
        </div>
        <div className="card">
          <div className="tile-label">Cards</div>
          <div className="tile-value">{live.length}</div>
          <div className="tile-note">{archived.length ? `${archived.length} archived` : "tracked by hand"}</div>
        </div>
      </section>

      <section className="grid" aria-label="Cards">
        {live.length === 0 && <div className="card empty">No cards yet. Add one below.</div>}
        {live.map((c) => (
          <CardPanel key={c.id} card={c} today={todayIso} act={act} />
        ))}
      </section>

      <AddCard onAdd={(body) => act(() => cards.add(body))} />

      {archived.length > 0 && (
        <details className="card">
          <summary className="muted">{archived.length} archived</summary>
          {archived.map((c) => (
            <div className="row" key={c.id} style={{ alignItems: "center" }}>
              <span>{c.name}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <button type="button" className="btn" onClick={() => act(() => cards.patch(c.id, { archived: false }))}>Restore</button>
                <button
                  type="button"
                  className="btn danger"
                  onClick={() => window.confirm(`Delete ${c.name} and all its bills?`) && act(() => cards.remove(c.id))}
                >
                  Delete
                </button>
              </span>
            </div>
          ))}
        </details>
      )}
    </>
  );
}

function CardPanel({ card: c, today, act }: { card: Card; today: string; act: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [mode, setMode] = useState<"" | "add" | "bills" | "edit">("");
  const [bills, setBills] = useState<Bill[]>([]);
  const toggle = (m: "add" | "bills" | "edit") => setMode(mode === m ? "" : m);
  const refreshBills = useCallback(() => {
    cards.bills(c.id).then(setBills).catch(() => undefined);
  }, [c.id]);
  // Keep the history in step with the card after any change (bill added, paid or removed).
  useEffect(() => {
    if (mode === "bills" || c.bills_count > 1) refreshBills();
  }, [mode, c.bills_count, c.unpaid_total, c.last_bill?.id, refreshBills]);

  const last = c.last_bill;
  const series = [...bills].reverse().slice(-12);

  return (
    <div className="card">
      <div className="row" style={{ alignItems: "baseline" }}>
        <h2 style={{ color: "var(--text)" }}>{c.name}</h2>
        <span className="muted">
          bill on the {ordinal(c.statement_day)}
          {c.due_days !== null ? `, due ${c.due_days} days later` : ""}
        </span>
      </div>

      <div className="kv">
        <span className="muted">Next bill</span>
        <span>
          {day(c.next_statement)} <span className="muted">· {inDays(c.days_to_statement)}</span>
        </span>
        <span className="muted">Last bill</span>
        <span>
          {last ? (
            <>
              <strong className="mono">{inr(last.amount)}</strong> <span className="muted">· generated {day(last.statement_date)}</span>
            </>
          ) : (
            <span className="muted">none recorded yet</span>
          )}
        </span>
        {last && (
          <>
            <span className="muted">Status</span>
            <span style={{ color: statusColor(last) }}>
              {statusText(last)}
              {last.due_date && last.status !== "paid" ? <span className="muted"> · {day(last.due_date)}</span> : ""}
              {last.min_due !== null && last.status !== "paid" ? <span className="muted"> · min {inr(last.min_due)}</span> : ""}
            </span>
          </>
        )}
        {c.unpaid_count > 1 && (
          <>
            <span className="muted">Unpaid</span>
            <span className="mono">{inr(c.unpaid_total)} <span className="muted">across {c.unpaid_count} bills</span></span>
          </>
        )}
      </div>

      {series.length >= 2 && <div className="tile-note">Bill amount by the month it was generated</div>}
      {series.length >= 2 && (
        <Chart
          kind="bars"
          data={{
            columns: ["month", "amount"],
            rows: series.map((b) => [b.statement_date.slice(0, 7), b.amount]),
            chart: "bars",
            value_col: 1,
            time: true,
          }}
        />
      )}

      <div className="tile-tools">
        <button type="button" className="btn primary" onClick={() => toggle("add")} aria-expanded={mode === "add"}>Add bill</button>
        <button type="button" className="btn" onClick={() => toggle("bills")} aria-expanded={mode === "bills"}>
          Bills ({c.bills_count})
        </button>
        <button type="button" className="btn" onClick={() => toggle("edit")} aria-expanded={mode === "edit"}>Edit</button>
        <button type="button" className="btn" onClick={() => act(() => cards.patch(c.id, { archived: true }))}>Archive</button>
      </div>

      {mode === "add" && (
        <BillForm
          card={c}
          today={today}
          onSave={(body) =>
            act(async () => {
              await cards.addBill(c.id, body);
              setMode("");
            })
          }
        />
      )}
      {mode === "edit" && (
        <EditForm
          card={c}
          onSave={(body) =>
            act(async () => {
              await cards.patch(c.id, body);
              setMode("");
            })
          }
        />
      )}
      {mode === "bills" && (
        <div>
          {bills.length === 0 && <div className="muted">No bills yet.</div>}
          {bills.map((b) => (
            <div className="bill-row" key={b.id}>
              <span className="muted">{day(b.statement_date)}</span>
              <span className="mono">{inr(b.amount)}</span>
              <span style={{ color: statusColor(b) }}>{statusText(b)}</span>
              <span style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn"
                  onClick={() => act(async () => { await cards.patchBill(b.id, { paid: b.status !== "paid" }); refreshBills(); })}
                >
                  {b.status === "paid" ? "Unpay" : "Mark paid"}
                </button>
                <button
                  type="button"
                  className="btn danger"
                  onClick={() => act(async () => { await cards.removeBill(b.id); refreshBills(); })}
                >
                  Remove
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function BillForm({
  card,
  today,
  onSave,
}: {
  card: Card;
  today: string;
  onSave: (b: { statement_date: string; amount: number; min_due: number | null; due_date: string | null }) => void;
}) {
  const [statement, setStatement] = useState(card.last_statement);
  const [amount, setAmount] = useState("");
  const [minDue, setMinDue] = useState("");
  const [due, setDue] = useState(card.suggested_due ?? "");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const a = num(amount);
    if (a === null || Number.isNaN(a) || a < 0) return;
    onSave({ statement_date: statement, amount: a, min_due: num(minDue), due_date: due || null });
  };
  return (
    <form className="filters" onSubmit={submit}>
      <label className="field">
        Bill generated on
        <input type="date" value={statement} max={today} onChange={(e) => setStatement(e.target.value)} required />
      </label>
      <label className="field">
        Total due (₹)
        <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus required />
      </label>
      <label className="field">
        Minimum due (₹, optional)
        <input inputMode="decimal" value={minDue} onChange={(e) => setMinDue(e.target.value)} />
      </label>
      <label className="field">
        Due date
        <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      </label>
      <button type="submit" className="btn primary">Save bill</button>
    </form>
  );
}

function EditForm({
  card,
  onSave,
}: {
  card: Card;
  onSave: (b: { name: string; statement_day: number; due_days: number | null }) => void;
}) {
  const [name, setName] = useState(card.name);
  const [stmtDay, setStmtDay] = useState(String(card.statement_day));
  const [dueDays, setDueDays] = useState(card.due_days === null ? "" : String(card.due_days));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const d = Number(stmtDay);
    if (!name.trim() || !(d >= 1 && d <= 31)) return;
    onSave({ name: name.trim(), statement_day: d, due_days: num(dueDays) });
  };
  return (
    <form className="filters" onSubmit={submit}>
      <label className="field">
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        Bill day of month
        <input inputMode="numeric" value={stmtDay} onChange={(e) => setStmtDay(e.target.value)} style={{ width: 120 }} />
      </label>
      <label className="field">
        Days to pay (optional)
        <input inputMode="numeric" value={dueDays} onChange={(e) => setDueDays(e.target.value)} style={{ width: 140 }} />
      </label>
      <button type="submit" className="btn primary">Save</button>
    </form>
  );
}

function AddCard({ onAdd }: { onAdd: (b: { name: string; statement_day: number; due_days: number | null }) => void }) {
  const [name, setName] = useState("");
  const [stmtDay, setStmtDay] = useState("");
  const [dueDays, setDueDays] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const d = Number(stmtDay);
    if (!name.trim() || !(d >= 1 && d <= 31)) return;
    onAdd({ name: name.trim(), statement_day: d, due_days: num(dueDays) });
    setName("");
    setStmtDay("");
    setDueDays("");
  };
  return (
    <form className="card" onSubmit={submit} aria-label="Add a card">
      <h2>Add a card</h2>
      <div className="filters">
        <label className="field">
          Card
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="HSBC Live+" />
        </label>
        <label className="field">
          Bill generated on day
          <input inputMode="numeric" value={stmtDay} onChange={(e) => setStmtDay(e.target.value)} placeholder="1 to 31" style={{ width: 140 }} />
        </label>
        <label className="field">
          Days to pay after (optional)
          <input inputMode="numeric" value={dueDays} onChange={(e) => setDueDays(e.target.value)} placeholder="18" style={{ width: 170 }} />
        </label>
        <button type="submit" className="btn primary">Add card</button>
      </div>
    </form>
  );
}

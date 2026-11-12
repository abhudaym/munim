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

// Dark enough that white text stays readable on every one.
const FACES = [
  { hex: "#2b2f36", name: "Graphite" },
  { hex: "#1f3a8a", name: "Blue" },
  { hex: "#0f5c55", name: "Teal" },
  { hex: "#1d5c2e", name: "Green" },
  { hex: "#7a1f2b", name: "Maroon" },
  { hex: "#4c2a85", name: "Purple" },
  { hex: "#8a4a0c", name: "Copper" },
  { hex: "#6b5200", name: "Gold" },
];
/** A card with no colour picked gets one from its name, so it stays the same every time. */
const faceColor = (c: { name: string; color: string | null }) => {
  if (c.color) return c.color;
  let h = 0;
  for (const ch of c.name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return FACES[h % FACES.length].hex;
};

/** The card drawn as a card: your own picture if you added one, else a plain coloured face. */
function CardFace({ card: c }: { card: Card }) {
  if (c.image_url) return <img className="face" src={c.image_url} alt={`${c.name} card`} />;
  return (
    <div className="face" style={{ background: faceColor(c) }} role="img" aria-label={`${c.name} card`}>
      <span className="face-chip" aria-hidden="true" />
      <span className="face-num">•••• •••• •••• {c.last4 ?? "••••"}</span>
      <span className="face-foot">
        <span className="face-name">{c.name}</span>
        <span>BILL {ordinal(c.statement_day).toUpperCase()}</span>
      </span>
    </div>
  );
}

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

      <div className="face-row">
      <CardFace card={c} />
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
          onImage={(file) => act(() => (file ? cards.setImage(c.id, file) : cards.removeImage(c.id)))}
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

type CardEdit = { name: string; statement_day: number; due_days: number | null; color: string | null; last4: string | null };

function EditForm({ card, onSave, onImage }: { card: Card; onSave: (b: CardEdit) => void; onImage: (file: File | null) => void }) {
  const [name, setName] = useState(card.name);
  const [stmtDay, setStmtDay] = useState(String(card.statement_day));
  const [dueDays, setDueDays] = useState(card.due_days === null ? "" : String(card.due_days));
  const [last4, setLast4] = useState(card.last4 ?? "");
  const [color, setColor] = useState(faceColor(card));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const d = Number(stmtDay);
    if (!name.trim() || !(d >= 1 && d <= 31)) return;
    if (last4 !== "" && !/^\d{4}$/.test(last4)) return;
    onSave({ name: name.trim(), statement_day: d, due_days: num(dueDays), color, last4: last4 || null });
  };
  return (
    <form className="edit-card" onSubmit={submit}>
      <div className="filters">
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
        <label className="field">
          Last 4 digits (optional)
          <input inputMode="numeric" maxLength={4} value={last4} onChange={(e) => setLast4(e.target.value)} style={{ width: 150 }} />
        </label>
      </div>
      <div role="group" aria-label="Card colour" className="swatches">
        {FACES.map((f) => (
          <button
            type="button"
            key={f.hex}
            className="swatch-btn"
            style={{ background: f.hex }}
            aria-label={f.name}
            aria-pressed={color === f.hex}
            title={f.name}
            onClick={() => setColor(f.hex)}
          />
        ))}
      </div>
      <div className="filters">
        <button type="submit" className="btn primary">Save</button>
        <label className="btn filebtn">
          {card.image_url ? "Replace picture" : "Use my own picture"}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onImage(file);
              e.target.value = "";
            }}
          />
        </label>
        {card.image_url && (
          <button type="button" className="btn" onClick={() => onImage(null)}>Remove picture</button>
        )}
      </div>
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

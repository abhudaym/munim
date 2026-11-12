import { FormEvent, useCallback, useEffect, useState } from "react";
import { Account, AccountType, NetWorth as NW, Snapshot, worth } from "../api";
import Chart from "../components/Chart";
import { fmtDate, inr } from "../format";

const TYPES: { id: AccountType; label: string }[] = [
  { id: "cash", label: "Cash / bank" },
  { id: "equity", label: "Stocks" },
  { id: "mutual_fund", label: "Mutual funds" },
  { id: "debt", label: "Debt / PF / FD" },
  { id: "other", label: "Other" },
];
const typeLabel = (id: string) => TYPES.find((t) => t.id === id)?.label ?? id;
const STALE_DAYS = 35;
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const day = (iso: string) => fmtDate(`${iso}T00:00:00`);
const pct = (n: number) => `${n >= 0 ? "+" : ""}${(Math.round(n * 10) / 10).toFixed(1)}%`;

export default function NetWorth() {
  const [nw, setNw] = useState<NW | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState("");
  const [recording, setRecording] = useState<number | null>(null);
  const [history, setHistory] = useState<{ id: number; rows: Snapshot[] } | null>(null);

  const load = useCallback(() => {
    Promise.all([worth.networth(), worth.accounts()])
      .then(([n, a]) => {
        setNw(n);
        setAccounts(a);
      })
      .catch((e: Error) => setError(e.message));
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
  const showHistory = async (id: number) => {
    if (history?.id === id) return setHistory(null);
    try {
      setHistory({ id, rows: await worth.snapshots(id) });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!nw) return error ? <div className="banner error">Could not load: {error}</div> : <p className="muted">Loading…</p>;

  const live = accounts.filter((a) => !a.archived);
  const archived = accounts.filter((a) => a.archived);
  const gainPct = nw.gain !== null && nw.invested ? (nw.gain / nw.invested) * 100 : null;
  const hasHistory = nw.history.length >= 2;

  return (
    <>
      <div>
        <h1>
          Net worth <span className="muted">/ {nw.as_of ? `latest entry ${day(nw.as_of)}` : "nothing recorded yet"}</span>
        </h1>
      </div>
      {error && <div className="banner error">{error}</div>}

      <section className="tiles" aria-label="Net worth totals">
        <div className="card">
          <div className="tile-label">Net worth</div>
          <div className="tile-value">{inr(nw.total)}</div>
          <div className="tile-note">{live.filter((a) => a.value !== null).length} accounts with a value</div>
        </div>
        <div className="card">
          <div className="tile-label">Invested</div>
          <div className="tile-value">{nw.invested === null ? "–" : inr(nw.invested)}</div>
          <div className="tile-note">accounts that report it</div>
        </div>
        <div className="card">
          <div className="tile-label">Gain</div>
          <div className="tile-value" style={nw.gain === null ? undefined : { color: nw.gain < 0 ? "var(--bad)" : "var(--good)" }}>
            {nw.gain === null ? "–" : inr(nw.gain)}
          </div>
          <div className="tile-note">{gainPct === null ? "needs an invested amount" : `${pct(gainPct)} on invested`}</div>
        </div>
        <div className="card">
          <div className="tile-label">Put into investments</div>
          <div className="tile-value">{inr(nw.contributed_total)}</div>
          <div className="tile-note">from your Money Manager entries</div>
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h2>Net worth by month</h2>
          {hasHistory ? (
            <Chart
              kind="line"
              data={{
                columns: ["month", "total"],
                rows: nw.history.map((h) => [h.month, h.total]),
                chart: "line",
                value_col: 1,
                time: true,
              }}
            />
          ) : (
            <div className="muted">A line appears once there are entries in two different months.</div>
          )}
        </div>
        <div className="card">
          <h2>By type</h2>
          {nw.by_type.length === 0 && <div className="muted">Record a value for an account to see the split.</div>}
          {nw.by_type.map((t) => (
            <div className="bar-row" key={t.type}>
              <span>{typeLabel(t.type)}</span>
              <div className="track" aria-hidden="true">
                <div className="fill amber" style={{ width: `${t.share * 100}%` }} />
              </div>
              <span className="mono right">{Math.round(t.share * 100)}%</span>
              <span className="mono right">{inr(t.total)}</span>
            </div>
          ))}
          {nw.contributions.length > 0 && (
            <>
              <h2 style={{ marginTop: 8 }}>Put in per month</h2>
              <Chart
                kind="bars"
                data={{
                  columns: ["month", "amount"],
                  rows: nw.contributions.slice(-12).map((c) => [c.month, c.total]),
                  chart: "bars",
                  value_col: 1,
                  time: true,
                }}
              />
            </>
          )}
        </div>
      </section>

      <section className="card" aria-label="Accounts">
        <div className="row">
          <h2>Accounts</h2>
          <span className="muted">Values are typed in. Dhan and Upstox show them in the app.</span>
        </div>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Type</th>
                <th className="right">Value</th>
                <th className="right">Invested</th>
                <th className="right">Gain</th>
                <th>As of</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {live.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">No accounts yet. Add one below.</td>
                </tr>
              )}
              {live.map((a) => (
                <AccountRows
                  key={a.id}
                  account={a}
                  open={recording === a.id}
                  history={history?.id === a.id ? history.rows : null}
                  onRecord={() => setRecording(recording === a.id ? null : a.id)}
                  onHistory={() => void showHistory(a.id)}
                  onSave={(body) =>
                    act(async () => {
                      await worth.record(a.id, body);
                      setRecording(null);
                      if (history?.id === a.id) setHistory({ id: a.id, rows: await worth.snapshots(a.id) });
                    })
                  }
                  onArchive={() => act(() => worth.patchAccount(a.id, { archived: true }))}
                  onDeleteSnapshot={(id) =>
                    act(async () => {
                      await worth.deleteSnapshot(id);
                      setHistory({ id: a.id, rows: await worth.snapshots(a.id) });
                    })
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
        <AddAccount onAdd={(body) => act(() => worth.addAccount(body))} />
        {archived.length > 0 && (
          <details>
            <summary className="muted">{archived.length} archived</summary>
            {archived.map((a) => (
              <div className="row" key={a.id} style={{ alignItems: "center" }}>
                <span>
                  {a.name} <span className="muted">· {typeLabel(a.type)}</span>
                </span>
                <span style={{ display: "flex", gap: 8 }}>
                  <button type="button" className="btn" onClick={() => act(() => worth.patchAccount(a.id, { archived: false }))}>
                    Restore
                  </button>
                  <button
                    type="button"
                    className="btn danger"
                    onClick={() => window.confirm(`Delete ${a.name} and all its entries?`) && act(() => worth.deleteAccount(a.id))}
                  >
                    Delete
                  </button>
                </span>
              </div>
            ))}
          </details>
        )}
      </section>
    </>
  );
}

type RecordBody = { as_of: string; value: number; invested: number | null };

function AccountRows(props: {
  account: Account;
  open: boolean;
  history: Snapshot[] | null;
  onRecord: () => void;
  onHistory: () => void;
  onSave: (b: RecordBody) => void;
  onArchive: () => void;
  onDeleteSnapshot: (id: number) => void;
}) {
  const { account: a } = props;
  const stale = a.days_old !== null && a.days_old > STALE_DAYS;
  return (
    <>
      <tr>
        <td>{a.name}</td>
        <td className="muted">{typeLabel(a.type)}</td>
        <td className="mono right">{a.value === null ? <span className="muted">–</span> : inr(a.value)}</td>
        <td className="mono right">{a.invested === null ? <span className="muted">–</span> : inr(a.invested)}</td>
        <td className="mono right" style={a.gain === null ? undefined : { color: a.gain < 0 ? "var(--bad)" : "var(--good)" }}>
          {a.gain === null ? <span className="muted">–</span> : inr(a.gain)}
        </td>
        <td style={stale ? { color: "var(--accent)" } : undefined}>
          {a.as_of ? `${day(a.as_of)}${stale ? ` · ${a.days_old}d old` : ""}` : <span className="muted">never</span>}
        </td>
        <td className="right" style={{ whiteSpace: "nowrap" }}>
          <button type="button" className="btn" onClick={props.onRecord} aria-expanded={props.open}>
            Record value
          </button>{" "}
          <button type="button" className="btn" onClick={props.onHistory}>
            History
          </button>{" "}
          <button type="button" className="btn" onClick={props.onArchive}>
            Archive
          </button>
        </td>
      </tr>
      {props.open && (
        <tr>
          <td colSpan={7}>
            <RecordForm initial={a} onSave={props.onSave} />
          </td>
        </tr>
      )}
      {props.history && (
        <tr>
          <td colSpan={7}>
            {props.history.length === 0 && <span className="muted">No entries yet.</span>}
            {props.history.map((s) => (
              <div className="row" key={s.id} style={{ alignItems: "center" }}>
                <span className="muted">{day(s.as_of)}</span>
                <span className="mono">
                  {inr(s.value)}
                  {s.invested !== null && <span className="muted"> · invested {inr(s.invested)}</span>}
                </span>
                <button type="button" className="btn danger" onClick={() => props.onDeleteSnapshot(s.id)}>
                  Remove
                </button>
              </div>
            ))}
          </td>
        </tr>
      )}
    </>
  );
}

function RecordForm({ initial, onSave }: { initial: Account; onSave: (b: RecordBody) => void }) {
  const [asOf, setAsOf] = useState(today());
  const [value, setValue] = useState("");
  const [invested, setInvested] = useState(initial.invested === null ? "" : String(initial.invested));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const v = Number(value);
    if (value === "" || Number.isNaN(v) || v < 0) return;
    onSave({ as_of: asOf, value: v, invested: invested === "" ? null : Number(invested) });
  };
  return (
    <form className="filters" onSubmit={submit}>
      <label className="field">
        Date
        <input type="date" value={asOf} max={today()} onChange={(e) => setAsOf(e.target.value)} required />
      </label>
      <label className="field">
        Current value (₹)
        <input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} placeholder="1,20,000" autoFocus required />
      </label>
      {initial.type !== "cash" && (
        <label className="field">
          Invested so far (₹, optional)
          <input inputMode="decimal" value={invested} onChange={(e) => setInvested(e.target.value)} />
        </label>
      )}
      <button type="submit" className="btn primary">Save</button>
    </form>
  );
}

function AddAccount({ onAdd }: { onAdd: (b: { name: string; type: AccountType }) => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<AccountType>("equity");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onAdd({ name: name.trim(), type });
    setName("");
  };
  return (
    <form className="filters" onSubmit={submit} aria-label="Add an account">
      <label className="field">
        New account
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Dhan, EPF…" />
      </label>
      <label className="field">
        Type
        <select value={type} onChange={(e) => setType(e.target.value as AccountType)}>
          {TYPES.map((t) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
      </label>
      <button type="submit" className="btn">Add account</button>
    </form>
  );
}

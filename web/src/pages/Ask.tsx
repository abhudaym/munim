import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, AskHistoryItem, AskResult, AskStatus } from "../api";
import { inr, monthLabel } from "../format";

const SUGGESTIONS = [
  "How much did I spend on coffee this month?",
  "How much did I spend on coffee in the last three months?",
  "What are my top 5 spending categories this year?",
  "Spend per month over the last six months",
  "Which merchant did I spend the most at this year?",
];

const MONEY = /(amount|total|spent|spend|sum|avg|average|income|expense|max|min|cost)/i;
const isMonth = (v: unknown) => typeof v === "string" && /^\d{4}-\d{2}$/.test(v);

function cell(column: string, value: string | number | null) {
  if (value === null) return <span className="muted">–</span>;
  if (typeof value === "number") return MONEY.test(column) ? inr(value) : value.toLocaleString("en-IN");
  return isMonth(value) ? monthLabel(value) : value;
}

export default function Ask() {
  const [status, setStatus] = useState<AskStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [history, setHistory] = useState<AskHistoryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadHistory = useCallback(() => {
    api.askHistory().then(setHistory).catch(() => undefined);
  }, []);
  useEffect(() => {
    api.askStatus().then(setStatus).catch((e: Error) => setError(e.message));
    loadHistory();
  }, [loadHistory]);

  const submit = async (q: string) => {
    const text = q.trim();
    if (text.length < 3 || busy) return;
    setQuestion(text);
    setBusy(true);
    setError("");
    try {
      setResult(await api.ask(text));
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
      loadHistory();
    }
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit(question);
  };

  return (
    <>
      <header>
        <h1>Ask</h1>
        <p className="muted">Plain-English questions about your spending.</p>
      </header>

      {status && !status.ready && (
        <div className="banner" role="status">
          No model is configured. Add <code>ANTHROPIC_API_KEY</code> to <code>.env</code> and restart the server.
        </div>
      )}

      <form className="card ask-form" onSubmit={onSubmit}>
        <label htmlFor="q" className="muted">Your question</label>
        <div className="ask-row">
          <input
            id="q"
            value={question}
            maxLength={500}
            placeholder="How much did I spend on coffee this month?"
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="btn primary" disabled={busy || question.trim().length < 3 || status?.ready === false}>
            {busy ? "Thinking…" : "Ask"}
          </button>
        </div>
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button type="button" key={s} className="chip" onClick={() => void submit(s)} disabled={busy || status?.ready === false}>
              {s}
            </button>
          ))}
        </div>
      </form>

      {error && <div className="banner error" role="alert">{error}</div>}

      {result && (
        <section className="card" aria-live="polite">
          <h2>{result.question}</h2>
          {result.error && <div className="banner error">I couldn't answer that: {result.error}</div>}
          {!result.error && result.sql === null && <p>{result.note || "That's not something I can answer from your spending."}</p>}
          {result.headline !== null && (
            <div className="headline">{MONEY.test(result.columns[0]) ? inr(result.headline) : result.headline.toLocaleString("en-IN")}</div>
          )}
          {result.headline === null && result.columns.length > 0 && (
            <div className="scroll">
              <table>
                <thead>
                  <tr>{result.columns.map((c) => <th key={c} className={typeof result.rows[0]?.[result.columns.indexOf(c)] === "number" ? "right" : ""}>{c.replace(/_/g, " ")}</th>)}</tr>
                </thead>
                <tbody>
                  {result.rows.map((r, i) => (
                    <tr key={i}>
                      {r.map((v, j) => <td key={j} className={typeof v === "number" ? "right" : ""}>{cell(result.columns[j], v)}</td>)}
                    </tr>
                  ))}
                  {result.rows.length === 0 && <tr><td colSpan={result.columns.length} className="muted">No matching entries.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
          {result.truncated && <p className="muted">Showing the first {result.rows.length} rows.</p>}
          {result.note && result.sql !== null && <p className="muted">{result.note}</p>}
          {result.sql && (
            <details>
              <summary className="muted">Query that ran</summary>
              <pre className="sql">{result.sql}</pre>
            </details>
          )}
        </section>
      )}

      {history.length > 0 && (
        <section className="card">
          <h2>Recent questions</h2>
          <ul className="history">
            {history.map((h) => (
              <li key={h.id}>
                <button type="button" className="link" onClick={() => setQuestion(h.question)}>{h.question}</button>
                {h.error && <span className="muted"> · failed</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {status?.ready && (
        <p className="muted fine">
          Questions go to {status.model}, along with category names{status.sends_merchants ? ", frequent merchant names" : ""} and
          the date range. Amounts and individual transactions never leave this machine.
        </p>
      )}
    </>
  );
}

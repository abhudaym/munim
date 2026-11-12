import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, AskHistoryItem, AskResult, AskStatus } from "../api";
import Chart, { ChartPicker } from "../components/Chart";

const SUGGESTIONS = [
  "How much did I spend on coffee this month?",
  "How much did I spend on coffee in the last three months?",
  "What are my top 5 spending categories this year?",
  "Spend per month over the last six months",
  "Which merchant did I spend the most at this year?",
];

export default function Ask({ seed }: { seed: { text: string; n: number } }) {
  const [status, setStatus] = useState<AskStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [history, setHistory] = useState<AskHistoryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [kind, setKind] = useState("table");
  const [pinning, setPinning] = useState(false);
  const [title, setTitle] = useState("");
  const [rolling, setRolling] = useState(true);
  const [pinned, setPinned] = useState("");

  const loadHistory = useCallback(() => {
    api.askHistory().then(setHistory).catch(() => undefined);
  }, []);
  useEffect(() => {
    api.askStatus().then(setStatus).catch((e: Error) => setError(e.message));
    loadHistory();
  }, [loadHistory]);

  const [ran, setRan] = useState(0);
  const submit = async (q: string) => {
    const text = q.trim();
    if (text.length < 3 || busy) return;
    setQuestion(text);
    setBusy(true);
    setError("");
    try {
      const answer = await api.ask(text);
      setResult(answer);
      setKind(answer.chart);
      setPinning(false);
      setPinned("");
      setTitle(text.replace(/\?$/, "").slice(0, 120));
      setRolling(true);
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
      loadHistory();
    }
  };
  useEffect(() => {
    if (seed.n > ran && seed.text) {
      setRan(seed.n);
      void submit(seed.text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed.n]);
  const pin = async () => {
    if (!result?.sql || !title.trim()) return;
    try {
      await api.pinTile({ title: title.trim(), question: result.question, sql: result.sql, chart: kind, rolling });
      setPinning(false);
      setPinned(title.trim());
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const canPin = !!result && !result.error && !!result.sql && result.rows.length > 0;
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
          No model is configured. Pick one in <code>.env</code> (see <code>.env.example</code>) and restart the server.
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
          {!result.error && result.sql !== null && (
            <>
              <div className="row" style={{ alignItems: "center", margin: "12px 0" }}>
                <ChartPicker options={result.charts} value={kind} onChange={setKind} label="Show as" />
                {canPin && !pinning && (
                  <button type="button" className="btn" onClick={() => setPinning(true)}>Pin to dashboard</button>
                )}
              </div>
              <Chart data={result} kind={kind} />
            </>
          )}
          {result.truncated && <p className="muted">Showing the first {result.rows.length} rows.</p>}
          {result.note && result.sql !== null && <p className="muted">{result.note}</p>}
          {pinning && (
            <div className="card pin">
              <label className="field">
                Tile title
                <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
              </label>
              {result.rolling && (
                <label className="field">
                  Dates
                  <select value={rolling ? "rolling" : "fixed"} onChange={(e) => setRolling(e.target.value === "rolling")}>
                    <option value="rolling">Rolling: moves with today</option>
                    <option value="fixed">Fixed: the dates in this answer</option>
                  </select>
                </label>
              )}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <button type="button" className="btn primary" disabled={!title.trim()} onClick={() => void pin()}>Add to dashboard</button>
                <button type="button" className="btn" onClick={() => setPinning(false)}>Cancel</button>
                <span className="muted fine">The saved query re-runs on this machine. The model is not called again.</span>
              </div>
            </div>
          )}
          {pinned && (
            <div className="banner ok" role="status">Pinned “{pinned}”. <a href="#dashboard">Open the dashboard</a></div>
          )}
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

      {status?.ready && status.local && (
        <p className="muted fine">Answered by {status.model} running on this machine. Nothing leaves it.</p>
      )}
      {status?.ready && !status.local && (
        <p className="muted fine">
          Questions go to {status.model}, along with category names{status.sends_merchants ? ", frequent merchant names" : ""} and
          the date range. Amounts and individual transactions never leave this machine.
        </p>
      )}
    </>
  );
}

import { maskText } from "../privacy";
import { FormEvent, useEffect, useState } from "react";
import { analyseApi, AnalyseResult, AnalyseStatus } from "../api";

const SUGGESTIONS = [
  "Is my spending too much for my income?",
  "Where is my money going, and what changed lately?",
  "Am I saving enough?",
];

/** The answer as written: lines starting with "- " become a list, the rest are paragraphs. */
function Answer({ text }: { text: string }) {
  const blocks: { list: boolean; lines: string[] }[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const list = /^[-*•] /.test(line);
    const body = list ? line.replace(/^[-*•] /, "") : line;
    const last = blocks[blocks.length - 1];
    if (last && last.list && list) last.lines.push(body);
    else blocks.push({ list, lines: [body] });
  }
  return (
    <div className="answer">
      {blocks.map((b, i) =>
        b.list ? (
          <ul key={i}>{b.lines.map((l, j) => <li key={j}>{maskText(l)}</li>)}</ul>
        ) : (
          <p key={i}>{maskText(b.lines[0])}</p>
        ),
      )}
    </div>
  );
}

export default function Analyse() {
  const [status, setStatus] = useState<AnalyseStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [withGoal, setWithGoal] = useState(false);
  const [goalLabel, setGoalLabel] = useState("");
  const [goalAmount, setGoalAmount] = useState("");
  const [goalMonths, setGoalMonths] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalyseResult | null>(null);

  useEffect(() => {
    analyseApi.status().then(setStatus).catch((e: Error) => setError(e.message));
  }, []);

  const amount = Number(goalAmount.replace(/,/g, ""));
  const months = Number(goalMonths);
  const goalOk = !withGoal || (amount > 0 && Number.isInteger(months) && months >= 1);

  const run = async (q: string) => {
    const text = q.trim();
    if (text.length < 3 || busy || !goalOk) return;
    setQuestion(text);
    setBusy(true);
    setError("");
    try {
      setResult(
        await analyseApi.run({
          question: text,
          ...(withGoal ? { goal_amount: amount, goal_months: months, goal_label: goalLabel.trim() || undefined } : {}),
        }),
      );
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void run(question);
  };
  const blocked = status !== null && !status.ready;

  return (
    <>
      {blocked && (
        <div className="banner" role="status">
          {status?.problem ?? "Analyse is not ready."}
        </div>
      )}

      <form className="card ask-form" onSubmit={onSubmit}>
        <label htmlFor="aq" className="muted">What do you want to understand?</label>
        <div className="ask-row">
          <input
            id="aq"
            value={question}
            maxLength={500}
            placeholder="Is my spending too much for my income?"
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="btn primary" disabled={busy || question.trim().length < 3 || blocked || !goalOk}>
            {busy ? "Working…" : "Analyse"}
          </button>
        </div>
        <label className="check">
          <input type="checkbox" checked={withGoal} onChange={(e) => setWithGoal(e.target.checked)} /> Saving for something
        </label>
        {withGoal && (
          <div className="filters">
            <label className="field">
              What
              <input value={goalLabel} maxLength={80} onChange={(e) => setGoalLabel(e.target.value)} placeholder="a Europe trip" />
            </label>
            <label className="field">
              Cost (₹)
              <input inputMode="decimal" value={goalAmount} onChange={(e) => setGoalAmount(e.target.value)} placeholder="3,00,000" />
            </label>
            <label className="field">
              In how many months
              <input inputMode="numeric" value={goalMonths} onChange={(e) => setGoalMonths(e.target.value)} placeholder="10" style={{ width: 160 }} />
            </label>
            {!goalOk && (goalAmount || goalMonths) && <span className="muted">Enter a cost and a whole number of months.</span>}
          </div>
        )}
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button type="button" key={s} className="chip" onClick={() => void run(s)} disabled={busy || blocked}>
              {s}
            </button>
          ))}
        </div>
        {busy && <p className="muted fine">A local model is reading your numbers. This can take up to a minute.</p>}
      </form>

      {error && <div className="banner error" role="alert">{error}</div>}

      {result && (
        <section className="card" aria-live="polite">
          <h2>{result.question}</h2>
          {result.flagged && (
            <div className="banner error" role="status">
              Check this answer: it mentions {maskText(result.unmatched.join(", "))}, which is not in the numbers below.
            </div>
          )}
          <Answer text={result.answer} />
          <details>
            <summary className="muted">Numbers it used ({result.facts.length})</summary>
            <table className="facts">
              <tbody>
                {result.facts.map((f) => (
                  <tr key={f.key}>
                    <td className="muted">{f.label}</td>
                    <td>{maskText(f.text)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          {result.queries.length > 0 && (
            <details>
              <summary className="muted">Extra queries Ask ran ({result.queries.length})</summary>
              {result.queries.map((q, i) => (
                <div key={i}>
                  <p>{q.question}</p>
                  {q.error ? <p className="muted">Could not answer: {q.error}</p> : <pre className="sql">{q.sql}</pre>}
                </div>
              ))}
            </details>
          )}
          <p className="muted fine">
            Written by {result.model} on this machine in {result.seconds}s
            {result.attempts > 1 ? ", second try after a number did not match" : ""}. Every number is checked against the
            facts above. Not financial advice.
          </p>
        </section>
      )}

      {status?.ready && !result && (
        <p className="muted fine">Uses {status.model} on this machine. Your amounts never leave it.</p>
      )}
    </>
  );
}

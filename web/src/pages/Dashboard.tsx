import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, AskStatus, Tile } from "../api";
import Chart, { ChartPicker } from "../components/Chart";

const Icon = ({ d }: { d: string }) => (
  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const size = (t: Tile) => (t.error ? "" : t.chart === "number" ? "small" : t.chart === "table" && t.columns.length > 3 ? "wide" : "");

function TileCard({ tile, first, last, onChange }: { tile: Tile; first: boolean; last: boolean; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(tile.title);
  const [error, setError] = useState("");

  const act = (work: Promise<unknown>) => work.then(onChange).catch((e: Error) => setError(e.message));
  const rename = () => {
    const next = title.trim();
    if (next && next !== tile.title) void act(api.patchTile(tile.id, { title: next }));
  };

  return (
    <article className={`card tile ${size(tile)}`}>
      <div className="tile-head">
        <h2>{tile.title}</h2>
        <button type="button" className="icon-btn" aria-expanded={open} aria-label={`Options for ${tile.title}`} onClick={() => setOpen(!open)}>
          <Icon d="M5 12h.01M12 12h.01M19 12h.01" />
        </button>
      </div>

      {tile.error ? <div className="banner error">This tile could not run: {tile.error}</div> : <Chart data={tile} />}
      {tile.truncated && <p className="muted fine">Showing the first {tile.rows.length} rows.</p>}
      <div className="muted tile-q">“{tile.question}”{tile.rolling ? " · rolling dates" : ""}</div>

      {open && (
        <div className="tile-tools">
          <label className="field" style={{ flex: "1 1 160px" }}>
            Title
            <input value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} onBlur={rename} onKeyDown={(e) => e.key === "Enter" && rename()} />
          </label>
          <ChartPicker options={tile.charts} value={tile.chart} label={`Show ${tile.title} as`} onChange={(chart) => void act(api.patchTile(tile.id, { chart }))} />
          <button type="button" className="icon-btn" aria-label="Move earlier" disabled={first} onClick={() => void act(api.patchTile(tile.id, { move: -1 }))}>
            <Icon d="M15 18l-6-6 6-6" />
          </button>
          <button type="button" className="icon-btn" aria-label="Move later" disabled={last} onClick={() => void act(api.patchTile(tile.id, { move: 1 }))}>
            <Icon d="M9 18l6-6-6-6" />
          </button>
          <button type="button" className="btn danger" onClick={() => void act(api.deleteTile(tile.id))}>Remove</button>
          <details style={{ flex: "1 1 100%" }}>
            <summary className="muted">Query</summary>
            <pre className="sql">{tile.sql}</pre>
          </details>
          {error && <div className="banner error" style={{ flex: "1 1 100%" }}>{error}</div>}
        </div>
      )}
    </article>
  );
}

export default function Dashboard() {
  const [tiles, setTiles] = useState<Tile[] | null>(null);
  const [status, setStatus] = useState<AskStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.dashboard().then(setTiles).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
    api.askStatus().then(setStatus).catch(() => undefined);
  }, [load]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const text = question.trim();
    if (text.length < 3 || busy) return;
    setBusy(true);
    setError("");
    try {
      const answer = await api.ask(text);
      if (answer.error || !answer.sql) throw new Error(answer.error || answer.note || "That can't be answered from your entries.");
      if (answer.rows.length === 0) throw new Error("That question has no matching entries yet, so there is nothing to pin.");
      await api.pinTile({ title: text.replace(/\?$/, "").slice(0, 120), question: answer.question, sql: answer.sql, chart: answer.chart });
      setQuestion("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <header>
        <h1>Dashboard</h1>
        <p className="muted">Every tile is a question you pinned. Tiles re-run on this machine each time you open the page.</p>
      </header>

      <form className="card ask-form" onSubmit={add}>
        <label htmlFor="add" className="muted">Add a tile by asking</label>
        <div className="ask-row">
          <input id="add" value={question} maxLength={500} placeholder="How much did I spend on delivery each month this year?" onChange={(e) => setQuestion(e.target.value)} />
          <button className="btn primary" disabled={busy || question.trim().length < 3 || status?.ready === false}>
            {busy ? "Thinking…" : "Ask and pin"}
          </button>
        </div>
        {status?.ready === false && <span className="muted fine">No model is configured, so new tiles can't be asked for. Existing tiles still work.</span>}
      </form>

      {error && <div className="banner error" role="alert">{error}</div>}

      {tiles && tiles.length === 0 && (
        <div className="card empty">Nothing pinned yet. Ask a question above, or pin an answer from the <a href="#ask">Ask</a> page.</div>
      )}
      <div className="dash">
        {tiles?.map((t, i) => (
          <TileCard key={`${t.id}:${t.title}:${t.chart}`} tile={t} first={i === 0} last={i === tiles.length - 1} onChange={load} />
        ))}
      </div>
    </>
  );
}

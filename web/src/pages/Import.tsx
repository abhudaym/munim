import { useCallback, useEffect, useState } from "react";
import { api, CategoryMapRow, ImportRecord, ImportResult, Kind, Sample } from "../api";
import { fmtDate, inr } from "../format";

type Tab = "new" | "updated" | "deleted";

export default function Import() {
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [done, setDone] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("new");
  const [over, setOver] = useState(false);
  const [history, setHistory] = useState<ImportRecord[]>([]);
  const [cmap, setCmap] = useState<CategoryMapRow[]>([]);

  const reload = useCallback(() => {
    api.imports().then(setHistory).catch((e: Error) => setError(e.message));
    api.categoryMap().then(setCmap).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(reload, [reload]);

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    setDone(null);
    setPreview(null);
    setFileName(file.name);
    setBusy(true);
    try {
      const result = await api.previewImport(file);
      setPreview(result);
      setTab(result.new ? "new" : result.updated ? "updated" : "deleted");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      setDone(await api.commitImport(preview.sha256));
      setPreview(null);
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const patch = (raw: string, body: { category?: string; kind?: Kind | "" }) =>
    api.patchCategory(raw, body).then(reload).catch((e: Error) => setError(e.message));

  const nothingToDo = preview && !preview.new && !preview.updated && !preview.deleted;

  return (
    <>
      <h1>Import</h1>

      <div
        className={`drop${over ? " over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          void choose(e.dataTransfer.files[0]);
        }}
      >
        <div>Drop a Money Manager export here</div>
        <label className="btn primary" style={{ cursor: "pointer" }}>
          {busy ? "Working…" : "Choose .xlsx file"}
          <input type="file" accept=".xlsx" disabled={busy} onChange={(e) => void choose(e.target.files?.[0])} />
        </label>
        <div className="muted">Overlapping exports are fine. Only the differences are applied.</div>
      </div>

      {error && <div className="banner error">{error}</div>}

      {done && (
        <div className="banner ok">
          Imported. {done.new} new, {done.updated} updated, {done.deleted} removed, {done.unchanged} unchanged.
        </div>
      )}

      {preview && (
        <section className="card" aria-label="Import preview">
          <div className="row" style={{ alignItems: "center" }}>
            <div>
              <h2>{fileName}</h2>
              <div className="muted">
                {preview.rows_in_file} rows
                {preview.range_start && preview.range_end && (
                  <>
                    {" "}
                    · {fmtDate(preview.range_start)} to {fmtDate(preview.range_end)}
                  </>
                )}
                {preview.skipped_rows > 0 && <> · {preview.skipped_rows} rows skipped (missing date, amount or category)</>}
              </div>
            </div>
          </div>

          <div className="tiles">
            <Count label="New" value={preview.new} />
            <Count label="Updated" value={preview.updated} />
            <Count label="Removed in app" value={preview.deleted} />
            <Count label="Unchanged" value={preview.unchanged} />
          </div>

          {nothingToDo && <div className="banner">Nothing to import. This file matches what is already in the database.</div>}

          {preview.new_categories.length > 0 && (
            <div>
              <div className="muted" style={{ marginBottom: 6 }}>
                New categories, added on commit. Investments and EMI start as transfers. Adjust under Categories below.
              </div>
              {preview.new_categories.map((c) => (
                <span className="chip" key={c} style={{ marginRight: 6 }}>
                  {c}
                </span>
              ))}
            </div>
          )}

          {!nothingToDo && (
            <>
              <div className="tabs">
                {(["new", "updated", "deleted"] as const).map((t) => (
                  <button key={t} type="button" className="btn" aria-pressed={tab === t} onClick={() => setTab(t)}>
                    {t === "deleted" ? "removed" : t} ({preview[t]})
                  </button>
                ))}
              </div>
              <Samples preview={preview} tab={tab} />
            </>
          )}

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <button type="button" className="btn primary" disabled={busy} onClick={() => void commit()}>
              {nothingToDo ? "Record import anyway" : `Commit ${preview.new + preview.updated + preview.deleted} changes`}
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => setPreview(null)}>
              Cancel
            </button>
          </div>
        </section>
      )}

      <details className="card">
        <summary>
          <h2>Categories</h2>
          <span className="muted">{cmap.length} · rename or change what counts as spend</span>
        </summary>
        <div className="muted">
          Rename a category or change what it counts as. Transfers (SIPs, EMIs) stay out of spend totals. Changes apply to
          every stored entry.
        </div>
        <div className="scroll">
          <table className="cmap">
            <thead>
              <tr>
                <th>As exported</th>
                <th>Name</th>
                <th>Counts as</th>
              </tr>
            </thead>
            <tbody>
              {cmap.map((c) => (
                <tr key={c.raw_category}>
                  <td className="muted">{c.raw_category}</td>
                  <td>
                    <input
                      key={c.category}
                      aria-label={`Name for ${c.raw_category}`}
                      defaultValue={c.category}
                      onBlur={(e) => {
                        const v = e.target.value.trim();
                        if (v && v !== c.category) void patch(c.raw_category, { category: v });
                      }}
                    />
                  </td>
                  <td>
                    <select
                      aria-label={`Kind for ${c.raw_category}`}
                      value={c.kind ?? ""}
                      onChange={(e) => void patch(c.raw_category, { kind: e.target.value as Kind | "" })}
                    >
                      <option value="">Follow the entry (income or expense)</option>
                      <option value="expense">Expense</option>
                      <option value="income">Income</option>
                      <option value="transfer">Transfer</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {cmap.length === 0 && <div className="empty">Categories appear after the first import.</div>}
      </details>

      <section className="card">
        <h2>Import history</h2>
        {history.length === 0 ? (
          <div className="empty">No imports yet.</div>
        ) : (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>File</th>
                  <th>Covers</th>
                  <th className="right">New</th>
                  <th className="right">Updated</th>
                  <th className="right">Removed</th>
                  <th className="right">Unchanged</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td className="muted">{fmtDate(h.imported_at + "Z")}</td>
                    <td>{h.filename}</td>
                    <td className="muted">
                      {h.range_start && h.range_end ? `${fmtDate(h.range_start)} – ${fmtDate(h.range_end)}` : "—"}
                    </td>
                    <td className="mono right">{h.n_new}</td>
                    <td className="mono right">{h.n_updated}</td>
                    <td className="mono right">{h.n_deleted}</td>
                    <td className="mono right">{h.n_unchanged}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
    </div>
  );
}

function Samples({ preview, tab }: { preview: ImportResult; tab: Tab }) {
  const rows = preview.samples[tab];
  const total = preview[tab];
  if (rows.length === 0) return <div className="empty">Nothing in this group.</div>;

  const note = (s: Sample) => s.note ?? <span className="muted">no note</span>;
  return (
    <div>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Entry</th>
              <th>Category</th>
              <th className="right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {tab === "updated"
              ? preview.samples.updated.map((s, i) => (
                  <tr key={i}>
                    <td>{fmtDate(s.txn_ts)}</td>
                    <td>
                      {note(s)}
                      {s.restored ? (
                        <div className="sub">was removed, now back</div>
                      ) : (
                        s.was.note !== s.note && <div className="sub">was: {s.was.note ?? "no note"}</div>
                      )}
                    </td>
                    <td>
                      {s.category}
                      {s.was.category !== s.category && <div className="sub">was: {s.was.category}</div>}
                    </td>
                    <td className="mono right">
                      {inr(s.amount)}
                      {s.was.amount !== s.amount && <div className="sub">was {inr(s.was.amount)}</div>}
                    </td>
                  </tr>
                ))
              : (rows as Sample[]).map((s, i) => (
                  <tr key={i}>
                    <td>{fmtDate(s.txn_ts)}</td>
                    <td>{note(s)}</td>
                    <td>{s.category}</td>
                    <td className="mono right">{inr(s.amount)}</td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {total > rows.length && <div className="muted">Showing {rows.length} of {total}.</div>}
    </div>
  );
}

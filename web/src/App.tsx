import { FormEvent, useEffect, useState } from "react";
import { api, ImportRecord } from "./api";
import Overview from "./pages/Overview";
import NetWorth from "./pages/NetWorth";
import Transactions from "./pages/Transactions";
import Import from "./pages/Import";
import Ask from "./pages/Ask";
import Dashboard from "./pages/Dashboard";
import { fmtDate } from "./format";

const PAGES = [
  { id: "overview", label: "Overview" },
  { id: "networth", label: "Net worth" },
  { id: "dashboard", label: "Dashboard" },
  { id: "ask", label: "Ask" },
  { id: "transactions", label: "Transactions" },
  { id: "import", label: "Import" },
] as const;
type PageId = (typeof PAGES)[number]["id"];

const fromHash = (): PageId => {
  const id = window.location.hash.slice(1);
  return PAGES.some((p) => p.id === id) ? (id as PageId) : "overview";
};

export default function App() {
  const [page, setPage] = useState<PageId>(fromHash);
  const [typed, setTyped] = useState("");
  const [seed, setSeed] = useState<{ text: string; n: number }>({ text: "", n: 0 });
  const [last, setLast] = useState<ImportRecord | null>(null);

  useEffect(() => {
    const onHash = () => setPage(fromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    api.imports().then((rows) => setLast(rows[0] ?? null)).catch(() => undefined);
  }, [page]);

  // The bar at the top asks from any page: it hands the question to Ask and opens it.
  const ask = (e: FormEvent) => {
    e.preventDefault();
    const text = typed.trim();
    if (text.length < 3) return;
    setSeed((s) => ({ text, n: s.n + 1 }));
    setTyped("");
    window.location.hash = "ask";
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">MUNIM</div>
        <nav className="nav" aria-label="Main">
          {PAGES.map((p, i) => (
            <a key={p.id} href={`#${p.id}`} aria-current={page === p.id ? "page" : undefined}>
              {i + 1} {p.label}
            </a>
          ))}
        </nav>
        <div className="status">{last ? `last import ${fmtDate(last.imported_at)}` : "nothing imported yet"}</div>
      </header>
      <form className="askbar" onSubmit={ask}>
        <label htmlFor="askbar">ask &gt;</label>
        <input
          id="askbar"
          type="text"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="how much did I spend on coffee in the last three months?"
        />
        <span className="muted">enter to run</span>
      </form>
      <main className="main">
        {page === "overview" && <Overview />}
        {page === "networth" && <NetWorth />}
        {page === "dashboard" && <Dashboard />}
        {page === "ask" && <Ask seed={seed} />}
        {page === "transactions" && <Transactions />}
        {page === "import" && <Import />}
      </main>
    </div>
  );
}

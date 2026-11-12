import { useEffect, useState } from "react";
import Overview from "./pages/Overview";
import Transactions from "./pages/Transactions";
import Import from "./pages/Import";
import Ask from "./pages/Ask";
import Dashboard from "./pages/Dashboard";

const PAGES = [
  { id: "overview", label: "Overview" },
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
  useEffect(() => {
    const onHash = () => setPage(fromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <div className="app">
      <nav className="nav" aria-label="Main">
        <div className="brand">Munim</div>
        {PAGES.map((p) => (
          <a key={p.id} href={`#${p.id}`} aria-current={page === p.id ? "page" : undefined}>
            {p.label}
          </a>
        ))}
      </nav>
      <main className="main">
        {page === "overview" && <Overview />}
        {page === "dashboard" && <Dashboard />}
        {page === "ask" && <Ask />}
        {page === "transactions" && <Transactions />}
        {page === "import" && <Import />}
      </main>
    </div>
  );
}

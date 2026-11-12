import type { Plot } from "./components/Chart";
export type Kind = "expense" | "income" | "transfer";

export type Txn = {
  id: number;
  txn_ts: string;
  kind: Kind;
  amount: number;
  category: string;
  subcategory: string | null;
  merchant: string | null;
  note_raw: string | null;
  description: string | null;
  odometer_km: number | null;
  deleted_at: string | null;
};
export type TxnPage = { total: number; amount_total: number; limit: number; offset: number; items: Txn[] };

export type SummaryRow = { key: string; total: number; count: number };
export type Summary = { group_by: string; total: number; count: number; rows: SummaryRow[] };

export type Sample = { txn_ts: string; amount: number; category: string; note: string | null };
export type ImportResult = {
  committed: boolean;
  sha256: string;
  rows_in_file: number;
  skipped_rows: number;
  range_start: string | null;
  range_end: string | null;
  new: number;
  updated: number;
  deleted: number;
  unchanged: number;
  new_categories: string[];
  already_imported: boolean;
  samples: {
    new: Sample[];
    updated: (Sample & { was: Sample; restored: boolean })[];
    deleted: Sample[];
  };
};
export type ImportRecord = {
  id: number;
  filename: string;
  imported_at: string;
  range_start: string | null;
  range_end: string | null;
  rows_in_file: number;
  n_new: number;
  n_updated: number;
  n_deleted: number;
  n_unchanged: number;
};
export type CategoryMapRow = { raw_category: string; category: string; kind: Kind | null };

export type AskResult = {
  question: string;
  sql: string | null;
  columns: string[];
  rows: (string | number | null)[][];
  truncated: boolean;
  note: string | null;
  error: string | null;
  attempts: number;
  headline: number | null;
  model: string | null;
  chart: string;
  charts: string[];
  value_col: number | null;
  time: boolean;
  plot: Plot | null;
  rolling: boolean;
};
export type Tile = {
  id: number;
  title: string;
  question: string;
  sql: string;
  rolling: boolean;
  chart: string;
  charts: string[];
  value_col: number | null;
  time: boolean;
  plot: Plot | null;
  columns: string[];
  rows: (string | number | null)[][];
  truncated: boolean;
  error: string | null;
};
export type AskStatus = { ready: boolean; model: string | null; local: boolean; sends_merchants: boolean };
export type AskHistoryItem = {
  id: number;
  asked_at: string;
  question: string;
  sql: string | null;
  row_count: number | null;
  error: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  dashboard: () => request<Tile[]>("/api/dashboard"),
  pinTile: (body: { title: string; question: string; sql: string; chart?: string; rolling?: boolean }) =>
    request<Tile>("/api/dashboard/tiles", json("POST", body)),
  patchTile: (id: number, body: { title?: string; chart?: string; move?: -1 | 1 }) =>
    request<Tile>(`/api/dashboard/tiles/${id}`, json("PATCH", body)),
  deleteTile: async (id: number) => {
    const res = await fetch(`/api/dashboard/tiles/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  },
  askStatus: () => request<AskStatus>("/api/ask/status"),
  askHistory: () => request<AskHistoryItem[]>("/api/ask/history?limit=8"),
  ask: (question: string) =>
    request<AskResult>("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
  summary: (p: {
    group_by: string;
    from?: string;
    to?: string;
    kind?: string;
    category?: string;
    subcategory?: string;
    merchant?: string;
    q?: string;
  }) =>
    request<Summary>(`/api/summary${qs(p)}`),
  transactions: (p: Record<string, string | number | undefined>) =>
    request<TxnPage>(`/api/transactions${qs(p)}`),
  previewImport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportResult>("/api/imports?dry_run=true", { method: "POST", body: form });
  },
  commitImport: (sha256: string) =>
    request<ImportResult>(`/api/imports/${sha256}/commit`, { method: "POST" }),
  imports: () => request<ImportRecord[]>("/api/imports"),
  categoryMap: () => request<CategoryMapRow[]>("/api/category-map"),
  patchCategory: (raw: string, body: { category?: string; kind?: Kind | "" }) =>
    request<CategoryMapRow>(`/api/category-map/${encodeURIComponent(raw)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};

export type AccountType = "cash" | "equity" | "mutual_fund" | "debt" | "other";
export type Account = {
  id: number;
  name: string;
  type: AccountType;
  archived: boolean;
  value: number | null;
  invested: number | null;
  gain: number | null;
  as_of: string | null;
  days_old: number | null;
};
export type Snapshot = { id: number; as_of: string; value: number; invested: number | null; note: string | null };
export type NetWorth = {
  total: number;
  as_of: string | null;
  invested: number | null;
  gain: number | null;
  by_type: { type: string; total: number; share: number }[];
  history: { month: string; total: number }[];
  contributions: { month: string; total: number }[];
  contributed_total: number;
};
const send = (method: string, body?: unknown) => (body === undefined ? { method } : json(method, body));
const gone = async (path: string) => {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
};
export const worth = {
  networth: () => request<NetWorth>("/api/networth"),
  accounts: () => request<Account[]>("/api/accounts"),
  addAccount: (body: { name: string; type: AccountType }) => request<Account>("/api/accounts", send("POST", body)),
  patchAccount: (id: number, body: { name?: string; type?: AccountType; archived?: boolean }) =>
    request<Account>(`/api/accounts/${id}`, send("PATCH", body)),
  deleteAccount: (id: number) => gone(`/api/accounts/${id}`),
  snapshots: (id: number) => request<Snapshot[]>(`/api/accounts/${id}/snapshots`),
  record: (id: number, body: { as_of: string; value: number; invested?: number | null; note?: string | null }) =>
    request<Snapshot>(`/api/accounts/${id}/snapshots`, send("POST", body)),
  deleteSnapshot: (id: number) => gone(`/api/snapshots/${id}`),
};

export type Bill = {
  id: number;
  statement_date: string;
  amount: number;
  min_due: number | null;
  due_date: string | null;
  paid_on: string | null;
  status: "paid" | "overdue" | "due";
  days_to_due: number | null;
};
export type Card = {
  id: number;
  name: string;
  statement_day: number;
  due_days: number | null;
  color: string | null;
  last4: string | null;
  image_url: string | null;
  archived: boolean;
  next_statement: string;
  days_to_statement: number;
  last_statement: string;
  suggested_due: string | null;
  last_bill: Bill | null;
  unpaid_total: number;
  unpaid_count: number;
  next_due: string | null;
  bills_count: number;
};
export const cards = {
  list: () => request<Card[]>("/api/cards"),
  add: (body: { name: string; statement_day: number; due_days: number | null }) =>
    request<Card>("/api/cards", send("POST", body)),
  patch: (
    id: number,
    body: { name?: string; statement_day?: number; due_days?: number | null; color?: string | null; last4?: string | null; archived?: boolean },
  ) => request<Card>(`/api/cards/${id}`, send("PATCH", body)),
  setImage: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Card>(`/api/cards/${id}/image`, { method: "PUT", body: form });
  },
  removeImage: (id: number) => request<Card>(`/api/cards/${id}/image`, { method: "DELETE" }),
  remove: (id: number) => gone(`/api/cards/${id}`),
  bills: (id: number) => request<Bill[]>(`/api/cards/${id}/bills`),
  addBill: (id: number, body: { statement_date: string; amount: number; min_due?: number | null; due_date?: string | null }) =>
    request<Bill>(`/api/cards/${id}/bills`, send("POST", body)),
  patchBill: (id: number, body: { paid?: boolean; paid_on?: string; amount?: number; min_due?: number | null; due_date?: string | null }) =>
    request<Bill>(`/api/bills/${id}`, send("PATCH", body)),
  removeBill: (id: number) => gone(`/api/bills/${id}`),
};

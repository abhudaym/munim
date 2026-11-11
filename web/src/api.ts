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
  deleted_at: string | null;
};
export type TxnPage = { total: number; limit: number; offset: number; items: Txn[] };

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

export const api = {
  summary: (p: { group_by: string; from?: string; to?: string; kind?: string }) =>
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

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type HealthResponse = {
  status: string;
  app: string;
  environment: string;
  base_currency: string;
};

/** 后端 Decimal 可能序列化为 string 或 number,字段类型两头兼容。 */
type Num = string | number;

export type Account = {
  broker_account_id: string;
  name: string;
  base_currency: string;
  broker: string;
};

export type Position = {
  symbol: string;
  quantity: Num;
  cost_basis: Num;
  average_cost: Num;
  market_price: Num | null;
  market_value: Num | null;
  unrealized_pnl: Num | null;
};

export type Trade = {
  trade_id: string;
  symbol: string;
  side: string;
  quantity: Num;
  price: Num;
  proceeds_usd: Num;
  commission_usd: Num;
  realized_pnl_ibkr: Num | null;
  executed_at: string;
};

export type Pnl = {
  realized_pnl: Num;
  open_position_count: number;
  base_currency: string;
};

export type CurvePoint = {
  on_date: string;
  cumulative_pnl: Num;
  pct: Num | null;
};

export type AppendCount = { added: number; skipped: number };

export type AccountImport = {
  broker_account_id: string;
  instruments: AppendCount;
  trades: AppendCount;
  cash_flows: AppendCount;
  corporate_actions: AppendCount;
};

export type UploadReport = { accounts: AccountImport[] };

export type RefreshResult = {
  broker_account_id: string;
  snapshot_rows: number;
};

export type CurveMode = "A" | "B";

async function readError(res: Response, path: string): Promise<never> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: string };
    detail = body?.detail ? ` — ${body.detail}` : "";
  } catch {
    /* 非 JSON 响应,忽略 */
  }
  throw new Error(`API ${path} failed: ${res.status}${detail}`);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) return readError(res, path);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) return readError(res, path);
  return res.json() as Promise<T>;
}

export async function apiPostForm<T>(
  path: string,
  form: FormData,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    cache: "no-store",
    body: form,
  });
  if (!res.ok) return readError(res, path);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => apiGet<HealthResponse>("/health"),
  accounts: () => apiGet<Account[]>("/accounts"),
  positions: (id: string) =>
    apiGet<Position[]>(`/accounts/${encodeURIComponent(id)}/positions`),
  trades: (id: string) =>
    apiGet<Trade[]>(`/accounts/${encodeURIComponent(id)}/trades`),
  pnl: (id: string) =>
    apiGet<Pnl>(`/accounts/${encodeURIComponent(id)}/pnl`),
  curve: (id: string, mode: CurveMode) =>
    apiGet<CurvePoint[]>(
      `/accounts/${encodeURIComponent(id)}/curve?mode=${mode}`,
    ),
  refreshPrices: (id: string) =>
    apiPost<RefreshResult>(
      `/accounts/${encodeURIComponent(id)}/refresh-prices`,
    ),
  uploadStatement: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiPostForm<UploadReport>("/statements/upload", form);
  },
};

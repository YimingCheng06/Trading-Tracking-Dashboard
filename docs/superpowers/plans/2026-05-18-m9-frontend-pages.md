# M9 — 前端页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/upload` `/positions` `/trades` `/pnl` 四个占位页换成真页面,消费 M8 HTTP API;账户栏改成 `GET /accounts` 动态驱动。

**Architecture:** 数据页是服务端组件(`async`,`await searchParams`,`force-dynamic`),用 `lib/api.ts` 取后端数据;交互件(账户切换、刷新行情、上传、Mode 切换)是 `"use client"` 孤岛。选中账户用 URL search param `?account=<broker_account_id>` 共享。

**Tech Stack:** Next.js 16.2.4 App Router · React 19.2 · Tailwind v4 · Recharts。

**验证门(替代单元测试 —— 前端无测试框架):** 每个任务以 `cd frontend && npm run build` 通过(类型检查 + 编译)且 `npm run lint` 无错为完成判据。`force-dynamic` 页面不在 build 时执行,故 build 不需要后端在线。

**通用约定:**
- 工作目录是 worktree:`/Users/emmett/Documents/Trading-Tracking-Dashboard/.claude/worktrees/m9-frontend-pages`。
- 数值字段(Decimal)后端可能序列化成 string 或 number,统一用 `toNum()` 兼容两者。
- 设计语言参照 `frontend/app/(workspace)/dashboard/page.tsx` 与 `globals.css` 的 token(`--up` 绿、`--down` 红、`--accent` 蓝、`surface`/`border`/`muted`,数字加 `tabular` class)。
- 提交不加 `Co-Authored-By: Claude` trailer(项目 CLAUDE.md 规定)。

---

## Task 1: 基础层 — Recharts、API client、格式化、刷新图标

**Files:**
- Modify: `frontend/package.json`(加 recharts)
- Modify: `frontend/lib/api.ts`
- Create: `frontend/lib/format.ts`
- Modify: `frontend/app/(workspace)/_components/icons.tsx`(加 `IconRefresh`)

- [ ] **Step 1: 安装 Recharts**

Run: `cd frontend && npm install recharts`
若报 peer-dependency 冲突:`npm install recharts --legacy-peer-deps`。
确认 `package.json` 的 `dependencies` 多了 `recharts`。

- [ ] **Step 2: 重写 `lib/api.ts`**

完整替换文件内容:

```ts
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
```

- [ ] **Step 3: 创建 `lib/format.ts`**

```ts
/** 后端 Decimal 字段可能是 string 或 number;统一转 number。 */
export function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** USD 货币格式,带千位分隔与两位小数。null → "—"。 */
export function fmtMoney(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** 一般数量格式,最多 4 位小数。null → "—"。 */
export function fmtNum(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

/** 百分比:输入为分数(0.123 → "12.30%")。null → "—"。 */
export function fmtPct(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

/** ISO 日期/时间 → "YYYY-MM-DD"。 */
export function fmtDate(iso: string): string {
  return iso.slice(0, 10);
}

/** 盈亏着色 class:正绿、负红、零/空 muted。 */
export function pnlClass(v: string | number | null | undefined): string {
  const n = toNum(v);
  if (n === null || n === 0) return "text-muted-strong";
  return n > 0 ? "text-up" : "text-down";
}
```

- [ ] **Step 4: 加 `IconRefresh` 到 `icons.tsx`**

在 `icons.tsx` 末尾(`IconSearch` 之后)追加。环形双箭头,沿用 `Svg` 包装与 24×24 / stroke 1.6 风格:

```tsx
export function IconRefresh(p: IconProps) {
  return (
    <Svg {...p}>
      <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
      <path d="M3 21v-5h5" />
    </Svg>
  );
}
```

- [ ] **Step 5: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功、lint 无错。

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/lib/api.ts frontend/lib/format.ts "frontend/app/(workspace)/_components/icons.tsx"
git commit -m "M9: API client, formatters, Recharts, refresh icon"
```

---

## Task 2: 共享 UI 组件 — PageShell、DataTable、EmptyState

**Files:**
- Create: `frontend/app/(workspace)/_components/PageShell.tsx`
- Create: `frontend/app/(workspace)/_components/DataTable.tsx`
- Create: `frontend/app/(workspace)/_components/EmptyState.tsx`

- [ ] **Step 1: 创建 `PageShell.tsx`**

页头复用 `PlaceholderPage` 的视觉(group 小标 / 大标题 / 副标题 / 右上角图标方块),
但接受 `action`(右上角放按钮,如刷新)与 `children`(页面主体)。

```tsx
import type { ComponentType, ReactNode, SVGProps } from "react";

/**
 * 数据页统一外壳:页头(分组小标 + 标题 + 副标题 + 图标)+ 主体。
 * 与 PlaceholderPage 视觉一致,但承载真实内容与可选的页头操作区。
 */
export function PageShell({
  group,
  title,
  subtitle,
  icon: Icon,
  action,
  children,
}: {
  group: string;
  title: string;
  subtitle: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-6xl px-10 py-14">
      <header className="flex items-start justify-between gap-8">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
            {group}
          </p>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight">
            {title}
          </h1>
          <p className="mt-3 max-w-xl text-sm text-muted-strong">
            {subtitle}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {action}
          <div
            className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border/80 bg-surface text-accent"
            aria-hidden
          >
            <Icon width={24} height={24} />
          </div>
        </div>
      </header>
      <div className="mt-10">{children}</div>
    </div>
  );
}
```

- [ ] **Step 2: 创建 `DataTable.tsx`**

通用表格原语:暗色描边卡片包裹,表头小标 + 斑马行,数字列右对齐用 `tabular`。

```tsx
import type { ReactNode } from "react";

export type Column = {
  key: string;
  label: string;
  /** 右对齐(用于数字列) */
  numeric?: boolean;
};

/**
 * 轻量表格。rows 是已渲染好的单元格内容数组,顺序与 columns 对齐。
 * 表体可滚动 —— 适合成交流水这类长列表。
 */
export function DataTable({
  columns,
  rows,
}: {
  columns: Column[];
  rows: { id: string; cells: ReactNode[] }[];
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface/60">
      <div className="max-h-[68vh] overflow-y-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-rail/95 backdrop-blur">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`border-b border-border px-4 py-3 text-xs font-medium uppercase tracking-[0.14em] text-muted ${
                    c.numeric ? "text-right" : "text-left"
                  }`}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-border/40 transition-colors last:border-0 hover:bg-surface-elevated/60"
              >
                {row.cells.map((cell, i) => (
                  <td
                    key={columns[i].key}
                    className={`tabular px-4 py-3 ${
                      columns[i].numeric ? "text-right" : "text-left"
                    }`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 创建 `EmptyState.tsx`**

无账户 / 无数据 / 后端离线的统一占位。

```tsx
import type { ReactNode } from "react";

/**
 * 统一空态卡片。tone 控制强调色:
 * - "info" 普通空数据(accent 蓝)
 * - "warn" 后端离线 / 错误(down 红)
 */
export function EmptyState({
  tone = "info",
  title,
  hint,
  action,
}: {
  tone?: "info" | "warn";
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  const dot = tone === "warn" ? "bg-down" : "bg-accent";
  return (
    <section className="rounded-2xl border border-dashed border-border bg-surface/40 p-10">
      <div className="flex items-center gap-3">
        <span className={`inline-flex h-2 w-2 rounded-full ${dot}`} />
        <p className="text-sm font-medium text-muted-strong">{title}</p>
      </div>
      {hint && <p className="mt-3 max-w-md text-sm text-muted">{hint}</p>}
      {action && <div className="mt-6">{action}</div>}
    </section>
  );
}
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功、lint 无错。(组件未被引用会触发 lint 的 unused 吗?—— 它们是 `export`,不会。)

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/(workspace)/_components/PageShell.tsx" "frontend/app/(workspace)/_components/DataTable.tsx" "frontend/app/(workspace)/_components/EmptyState.tsx"
git commit -m "M9: shared PageShell / DataTable / EmptyState components"
```

---

## Task 3: 账户栏 DB 驱动 + URL 账户状态

**Files:**
- Modify: `frontend/app/(workspace)/layout.tsx`
- Modify: `frontend/app/(workspace)/_components/Sidebar.tsx`
- Modify: `frontend/app/(workspace)/_components/AccountRail.tsx`
- Modify: `frontend/app/(workspace)/_components/ModuleRail.tsx`
- Create: `frontend/lib/accounts.ts`(账户色板 + 派生工具)

**背景:** 当前 `Sidebar` 用 `useState` 存假账户。改成:`layout.tsx`(服务端)取 `GET /accounts` 传给 `Sidebar`;`AccountRail` 渲染真实账户,点击 pill 用 `router` 导航到 `?account=<broker_account_id>`;选中态从 `useSearchParams` 读。`useSearchParams` 需要 `<Suspense>` 边界。

- [ ] **Step 1: 创建 `lib/accounts.ts`**

```ts
import type { Account } from "./api";

/** 账户 pill 的固定色板,按账户索引取色。 */
const TINTS = ["#58a6ff", "#26a69a", "#c792ea", "#f0883e", "#e3b341"];

export function accountTint(index: number): string {
  return TINTS[index % TINTS.length];
}

/** broker_account_id 末 4 位作 pill 短标(如 "U23072637" → "2637")。 */
export function accountShort(account: Account): string {
  const id = account.broker_account_id;
  return id.length > 4 ? id.slice(-4) : id;
}
```

- [ ] **Step 2: 改 `layout.tsx` —— 服务端取账户传给 Sidebar**

```tsx
import { Suspense } from "react";
import { Sidebar } from "./_components/Sidebar";
import { api, type Account } from "@/lib/api";

export const dynamic = "force-dynamic";

async function getAccounts(): Promise<Account[]> {
  try {
    return await api.accounts();
  } catch {
    return [];
  }
}

/**
 * Workspace 壳:左侧 Discord 双栏 + 右侧页面。账户列表服务端拉取,
 * 失败降级为空数组(账户栏只剩 Logo + Add)。
 */
export default async function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const accounts = await getAccounts();

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Suspense fallback={<div style={{ width: "calc(var(--rail-width) + var(--module-width))" }} />}>
        <Sidebar accounts={accounts} />
      </Suspense>
      <main className="ambient-glow relative flex-1 overflow-y-auto">
        <div className="relative z-10">{children}</div>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: 改 `Sidebar.tsx` —— 收 accounts,选中态走 URL**

```tsx
"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { AccountRail } from "./AccountRail";
import { ModuleRail } from "./ModuleRail";
import type { Account } from "@/lib/api";

/**
 * Discord 双栏壳的协调者。选中账户存在 URL `?account=` 上,
 * 缺省落到第一个账户。点击 pill 在保持当前路径的前提下改 query。
 */
export function Sidebar({ accounts }: { accounts: Account[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const fromUrl = searchParams.get("account");
  const activeId =
    fromUrl ?? accounts[0]?.broker_account_id ?? "";

  function selectAccount(id: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("account", id);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex h-full flex-none">
      <AccountRail
        accounts={accounts}
        activeId={activeId}
        onSelect={selectAccount}
      />
      <ModuleRail activeAccountId={activeId} accounts={accounts} />
    </div>
  );
}
```

- [ ] **Step 4: 改 `AccountRail.tsx` —— 渲染真实账户**

替换组件签名与账户列表渲染。`Logo` / `Divider` / `AccountPill` / `AddButton` 内部子组件保留,
`AccountPill` 改为接受 `Account` 派生出的 `label`/`short`/`tint`:

```tsx
"use client";

import { useState } from "react";
import type { Account } from "@/lib/api";
import { accountTint, accountShort } from "@/lib/accounts";
import { IconPlus } from "./icons";

/**
 * 最左 72px 栏:账户切换器。账户来自 GET /accounts,选中态由父级
 * 从 URL 解析后下传。无账户时只显示 Logo + Add。
 */
export function AccountRail({
  accounts,
  activeId,
  onSelect,
}: {
  accounts: Account[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <aside
      className="relative flex h-full flex-col items-center gap-3 border-r border-black/40 bg-rail-deep py-4"
      style={{ width: "var(--rail-width)" }}
    >
      <Logo />
      <Divider />
      <ul className="flex flex-col gap-3">
        {accounts.map((acct, i) => (
          <li key={acct.broker_account_id}>
            <AccountPill
              label={acct.name}
              short={accountShort(acct)}
              tint={accountTint(i)}
              active={activeId === acct.broker_account_id}
              onClick={() => onSelect(acct.broker_account_id)}
            />
          </li>
        ))}
      </ul>
      <Divider />
      <AddButton />
    </aside>
  );
}
```

`Logo`、`Divider`、`AddButton` 三个内部组件原样保留(从现文件复制)。
`AccountPill` 内部组件原样保留(签名 `{label, short, tint, active, onClick}` 不变)。

- [ ] **Step 5: 改 `ModuleRail.tsx` —— 链接保留 `?account`,徽标用真实账户**

`ModuleRail` 现签名 `{ activeAccountId }`,改为 `{ activeAccountId, accounts }`。
顶部 `AccountBadge` 改成从 `accounts` 找当前账户取 `name`/`short`/`tint`(无账户时整个徽标不渲染)。
导航 `<Link>` 的 `href` 改为带上当前 `?account`:把 `item.href` 换成
`activeAccountId ? \`${item.href}?account=${encodeURIComponent(activeAccountId)}\` : item.href`,
`active` 判定仍只比 `pathname === item.href`(不含 query)。

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { moduleGroups } from "../_config/workspace";
import { accountTint, accountShort } from "@/lib/accounts";
import type { Account } from "@/lib/api";
import { IconSearch } from "./icons";

export function ModuleRail({
  activeAccountId,
  accounts,
}: {
  activeAccountId: string;
  accounts: Account[];
}) {
  const pathname = usePathname();
  const idx = accounts.findIndex(
    (a) => a.broker_account_id === activeAccountId,
  );
  const account = idx >= 0 ? accounts[idx] : null;

  return (
    <nav
      className="relative flex h-full flex-col items-center gap-2 border-r border-border/70 bg-rail py-4"
      style={{ width: "var(--module-width)" }}
    >
      {account && (
        <>
          <AccountBadge
            tint={accountTint(idx)}
            short={accountShort(account)}
            label={account.name}
          />
          <GroupDivider />
        </>
      )}
      <SearchButton />
      <GroupDivider />

      <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
        {moduleGroups.map((group, gi) => (
          <div key={group.id} className="flex flex-col items-center gap-1">
            {gi > 0 && <GroupDivider />}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              const href = activeAccountId
                ? `${item.href}?account=${encodeURIComponent(activeAccountId)}`
                : item.href;
              return (
                <div
                  key={item.id}
                  className="rail-group rail-item relative"
                  data-active={active}
                  data-hover
                >
                  <span className="rail-indicator" />
                  <Link
                    href={href}
                    className="flex items-center justify-center transition-all duration-150"
                    style={{
                      width: "var(--icon-size)",
                      height: "var(--icon-size)",
                      borderRadius: active
                        ? "var(--icon-radius-active)"
                        : "var(--icon-radius)",
                      background: active
                        ? "var(--accent-soft)"
                        : "transparent",
                      color: active ? "var(--accent)" : "var(--muted-strong)",
                    }}
                    aria-label={item.label}
                  >
                    <Icon width={20} height={20} />
                  </Link>
                  <span className="rail-tooltip">
                    {item.label}
                    <span className="ml-2 text-[10px] uppercase tracking-wider text-muted">
                      {group.label}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </nav>
  );
}
```

`AccountBadge`、`SearchButton`、`GroupDivider` 三个内部组件原样保留(从现文件复制)。
注意:删掉原来对 `accounts` 从 `../_config/workspace` 的 import(改从 `@/lib/api` 来类型)。

- [ ] **Step 6: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功、lint 无错。`useSearchParams` 已被 `layout.tsx` 的 `<Suspense>` 包裹,不应报 "missing suspense boundary"。

- [ ] **Step 7: Commit**

```bash
git add "frontend/app/(workspace)/layout.tsx" "frontend/app/(workspace)/_components/Sidebar.tsx" "frontend/app/(workspace)/_components/AccountRail.tsx" "frontend/app/(workspace)/_components/ModuleRail.tsx" frontend/lib/accounts.ts
git commit -m "M9: DB-driven account rail with URL-based account state"
```

---

## Task 4: `/positions` 页 + 刷新行情按钮

**Files:**
- Create: `frontend/app/(workspace)/_components/RefreshPricesButton.tsx`
- Modify: `frontend/app/(workspace)/positions/page.tsx`

- [ ] **Step 1: 创建 `RefreshPricesButton.tsx`**

带 `IconRefresh` 的「刷新行情」按钮(用户明确要求带「更新行情」图标)。点击调
`api.refreshPrices(id)`,成功后 `router.refresh()` 重取服务端数据;pending 时禁用 + 图标旋转;失败行内红字。

```tsx
"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { IconRefresh } from "./icons";

/**
 * 刷新行情按钮 —— 唯一触发后端联网(Yahoo)重建快照的入口。
 * 成功后 router.refresh() 让服务端组件用新快照重渲染。
 */
export function RefreshPricesButton({ accountId }: { accountId: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loading = busy || isPending;

  async function onClick() {
    setError(null);
    setBusy(true);
    try {
      await api.refreshPrices(accountId);
      startTransition(() => router.refresh());
    } catch (e) {
      setError(e instanceof Error ? e.message : "刷新失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={onClick}
        disabled={loading || !accountId}
        className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        <IconRefresh
          width={16}
          height={16}
          className={loading ? "animate-spin" : ""}
        />
        {loading ? "刷新中…" : "刷新行情"}
      </button>
      {error && <p className="text-xs text-down">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: 重写 `positions/page.tsx`**

服务端组件:`await searchParams` 取 `account`,缺省落第一个账户;取 `positions`;
渲染 `DataTable`。后端离线/无账户/无持仓走 `EmptyState`。

```tsx
import { api, type Account, type Position } from "@/lib/api";
import { fmtMoney, fmtNum, pnlClass } from "@/lib/format";
import { IconBriefcase } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { DataTable, type Column } from "../_components/DataTable";
import { EmptyState } from "../_components/EmptyState";
import { RefreshPricesButton } from "../_components/RefreshPricesButton";

export const dynamic = "force-dynamic";

const COLUMNS: Column[] = [
  { key: "symbol", label: "Symbol" },
  { key: "qty", label: "Qty", numeric: true },
  { key: "avg", label: "Avg Cost", numeric: true },
  { key: "cost", label: "Cost Basis", numeric: true },
  { key: "price", label: "Mkt Price", numeric: true },
  { key: "value", label: "Mkt Value", numeric: true },
  { key: "upnl", label: "Unrealized P&L", numeric: true },
];

export default async function PositionsPage({
  searchParams,
}: {
  searchParams: Promise<{ account?: string }>;
}) {
  const { account } = await searchParams;

  let accounts: Account[] = [];
  let offline = false;
  try {
    accounts = await api.accounts();
  } catch {
    offline = true;
  }
  const accountId = account ?? accounts[0]?.broker_account_id;

  let positions: Position[] = [];
  if (accountId && !offline) {
    try {
      positions = await api.positions(accountId);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Portfolio"
      title="Positions"
      subtitle="按 FIFO 重放得到的当前持仓;市值与未实现盈亏来自最近一次行情快照。"
      icon={IconBriefcase}
      action={accountId ? <RefreshPricesButton accountId={accountId} /> : null}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="后端离线"
          hint="无法连接 API。确认 backend 已在 :8000 运行。"
        />
      ) : !accountId ? (
        <EmptyState
          title="还没有账户"
          hint="先到 Upload 页导入一份 IBKR Flex 对账单。"
        />
      ) : positions.length === 0 ? (
        <EmptyState
          title="该账户暂无持仓"
          hint="导入对账单后,持仓会在这里出现。"
        />
      ) : (
        <DataTable
          columns={COLUMNS}
          rows={positions.map((p) => ({
            id: p.symbol,
            cells: [
              <span key="s" className="font-medium text-foreground">
                {p.symbol}
              </span>,
              fmtNum(p.quantity),
              fmtMoney(p.average_cost),
              fmtMoney(p.cost_basis),
              fmtMoney(p.market_price),
              fmtMoney(p.market_value),
              <span key="u" className={pnlClass(p.unrealized_pnl)}>
                {fmtMoney(p.unrealized_pnl)}
              </span>,
            ],
          }))}
        />
      )}
    </PageShell>
  );
}
```

- [ ] **Step 3: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功、lint 无错。

- [ ] **Step 4: Commit**

```bash
git add "frontend/app/(workspace)/_components/RefreshPricesButton.tsx" "frontend/app/(workspace)/positions/page.tsx"
git commit -m "M9: positions page with refresh-prices button"
```

---

## Task 5: `/trades` 页

**Files:**
- Modify: `frontend/app/(workspace)/trades/page.tsx`

- [ ] **Step 1: 重写 `trades/page.tsx`**

服务端组件,同 `/positions` 的账户解析模式。表列:Date / Symbol / Side / Qty / Price / Proceeds / Commission / Realized P&L。Side 用色块。

```tsx
import { api, type Account, type Trade } from "@/lib/api";
import { fmtMoney, fmtNum, fmtDate, pnlClass } from "@/lib/format";
import { IconArrowSwap } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { DataTable, type Column } from "../_components/DataTable";
import { EmptyState } from "../_components/EmptyState";

export const dynamic = "force-dynamic";

const COLUMNS: Column[] = [
  { key: "date", label: "Date" },
  { key: "symbol", label: "Symbol" },
  { key: "side", label: "Side" },
  { key: "qty", label: "Qty", numeric: true },
  { key: "price", label: "Price", numeric: true },
  { key: "proceeds", label: "Proceeds", numeric: true },
  { key: "commission", label: "Commission", numeric: true },
  { key: "rpnl", label: "Realized P&L", numeric: true },
];

function SideBadge({ side }: { side: string }) {
  const buy = side.toUpperCase() === "BUY";
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-xs font-medium ${
        buy ? "bg-up/15 text-up" : "bg-down/15 text-down"
      }`}
    >
      {side.toUpperCase()}
    </span>
  );
}

export default async function TradesPage({
  searchParams,
}: {
  searchParams: Promise<{ account?: string }>;
}) {
  const { account } = await searchParams;

  let accounts: Account[] = [];
  let offline = false;
  try {
    accounts = await api.accounts();
  } catch {
    offline = true;
  }
  const accountId = account ?? accounts[0]?.broker_account_id;

  let trades: Trade[] = [];
  if (accountId && !offline) {
    try {
      trades = await api.trades(accountId);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Activity"
      title="Trades"
      subtitle="导入对账单解析出的成交流水,按成交时间倒序。"
      icon={IconArrowSwap}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="后端离线"
          hint="无法连接 API。确认 backend 已在 :8000 运行。"
        />
      ) : !accountId ? (
        <EmptyState
          title="还没有账户"
          hint="先到 Upload 页导入一份 IBKR Flex 对账单。"
        />
      ) : trades.length === 0 ? (
        <EmptyState title="该账户暂无成交" hint="导入对账单后,成交会在这里出现。" />
      ) : (
        <DataTable
          columns={COLUMNS}
          rows={trades.map((t) => ({
            id: t.trade_id,
            cells: [
              fmtDate(t.executed_at),
              <span key="s" className="font-medium text-foreground">
                {t.symbol}
              </span>,
              <SideBadge key="side" side={t.side} />,
              fmtNum(t.quantity),
              fmtMoney(t.price),
              fmtMoney(t.proceeds_usd),
              fmtMoney(t.commission_usd),
              <span key="r" className={pnlClass(t.realized_pnl_ibkr)}>
                {fmtMoney(t.realized_pnl_ibkr)}
              </span>,
            ],
          }))}
        />
      )}
    </PageShell>
  );
}
```

- [ ] **Step 2: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功、lint 无错。

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/(workspace)/trades/page.tsx"
git commit -m "M9: trades page"
```

---

## Task 6: `/pnl` 页 + 净值曲线 + Mode 切换

**Files:**
- Create: `frontend/app/(workspace)/_components/EquityCurve.tsx`
- Create: `frontend/app/(workspace)/_components/CurveModeToggle.tsx`
- Modify: `frontend/app/(workspace)/pnl/page.tsx`

- [ ] **Step 1: 创建 `EquityCurve.tsx`(Recharts 包装,client component)**

```tsx
"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CurvePoint } from "@/lib/api";
import { toNum } from "@/lib/format";

/**
 * 净值曲线 —— 累计盈亏随日期变化的面积图。暗色网格 + accent 描边渐变填充。
 */
export function EquityCurve({ points }: { points: CurvePoint[] }) {
  const data = points.map((p) => ({
    date: p.on_date,
    pnl: toNum(p.cumulative_pnl) ?? 0,
  }));

  return (
    <div className="h-80 w-full rounded-2xl border border-border bg-surface/60 p-4">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#58a6ff" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#58a6ff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#2a313c" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#8b949e", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#2a313c" }}
            minTickGap={32}
          />
          <YAxis
            tick={{ fill: "#8b949e", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={64}
            tickFormatter={(v: number) => v.toLocaleString("en-US")}
          />
          <Tooltip
            contentStyle={{
              background: "#151b23",
              border: "1px solid #2a313c",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#b1bac4" }}
            formatter={(v: number) => [v.toLocaleString("en-US"), "Cumulative P&L"]}
          />
          <Area
            type="monotone"
            dataKey="pnl"
            stroke="#58a6ff"
            strokeWidth={2}
            fill="url(#pnlFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: 创建 `CurveModeToggle.tsx`(A/B 段控件,client component)**

```tsx
"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import type { CurveMode } from "@/lib/api";

const MODES: { value: CurveMode; label: string }[] = [
  { value: "A", label: "Mode A · TWR" },
  { value: "B", label: "Mode B · 净入金" },
];

/**
 * 净值曲线口径切换。改 URL `?mode=`,保留 `?account=`。
 */
export function CurveModeToggle({ mode }: { mode: CurveMode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function select(next: CurveMode) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("mode", next);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="inline-flex rounded-xl border border-border bg-surface p-1">
      {MODES.map((m) => {
        const active = m.value === mode;
        return (
          <button
            key={m.value}
            type="button"
            onClick={() => select(m.value)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              active
                ? "bg-accent-soft text-accent"
                : "text-muted hover:text-foreground"
            }`}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: 重写 `pnl/page.tsx`**

服务端组件,解析 `account` 与 `mode`(`?mode=A|B`,缺省 `B`);取 `pnl` 与 `curve`。
三张摘要卡(复用 dashboard 的 `Metric` 视觉,内联一个简化版)+ 曲线 + Mode 切换。

```tsx
import { api, type Account, type CurveMode, type CurvePoint, type Pnl } from "@/lib/api";
import { fmtMoney, pnlClass } from "@/lib/format";
import { IconTrendingUp } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { EmptyState } from "../_components/EmptyState";
import { EquityCurve } from "../_components/EquityCurve";
import { CurveModeToggle } from "../_components/CurveModeToggle";

export const dynamic = "force-dynamic";

function Metric({
  label,
  value,
  sublabel,
  valueClass,
}: {
  label: string;
  value: string;
  sublabel: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-6">
      <p className="text-xs uppercase tracking-[0.18em] text-muted">{label}</p>
      <p className={`tabular mt-3 text-3xl font-semibold tracking-tight ${valueClass ?? ""}`}>
        {value}
      </p>
      <p className="mt-1 text-xs text-muted">{sublabel}</p>
    </div>
  );
}

export default async function PnlPage({
  searchParams,
}: {
  searchParams: Promise<{ account?: string; mode?: string }>;
}) {
  const sp = await searchParams;
  const mode: CurveMode = sp.mode === "A" ? "A" : "B";

  let accounts: Account[] = [];
  let offline = false;
  try {
    accounts = await api.accounts();
  } catch {
    offline = true;
  }
  const accountId = sp.account ?? accounts[0]?.broker_account_id;

  let pnl: Pnl | null = null;
  let curve: CurvePoint[] = [];
  if (accountId && !offline) {
    try {
      [pnl, curve] = await Promise.all([
        api.pnl(accountId),
        api.curve(accountId, mode),
      ]);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Analysis"
      title="P&L"
      subtitle="已实现盈亏摘要与净值曲线。Mode A = IBKR/TWR;Mode B = 累计盈亏 ÷ 累计净入金。"
      icon={IconTrendingUp}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="后端离线"
          hint="无法连接 API。确认 backend 已在 :8000 运行。"
        />
      ) : !accountId || !pnl ? (
        <EmptyState
          title="还没有账户"
          hint="先到 Upload 页导入一份 IBKR Flex 对账单。"
        />
      ) : (
        <div className="space-y-8">
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Metric
              label="Realized P&L"
              value={fmtMoney(pnl.realized_pnl)}
              sublabel={pnl.base_currency}
              valueClass={pnlClass(pnl.realized_pnl)}
            />
            <Metric
              label="Open Positions"
              value={String(pnl.open_position_count)}
              sublabel="当前持仓数"
            />
            <Metric
              label="Base Currency"
              value={pnl.base_currency}
              sublabel="规范货币"
            />
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
                Equity Curve
              </h2>
              <CurveModeToggle mode={mode} />
            </div>
            {curve.length === 0 ? (
              <EmptyState
                title="暂无曲线数据"
                hint="需要先有成交与现金流;刷新行情后曲线会更完整。"
              />
            ) : (
              <EquityCurve points={curve} />
            )}
          </section>
        </div>
      )}
    </PageShell>
  );
}
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功、lint 无错。若 Recharts 触发 SSR/类型问题,确认 `EquityCurve.tsx` 顶部有 `"use client"`。

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/(workspace)/_components/EquityCurve.tsx" "frontend/app/(workspace)/_components/CurveModeToggle.tsx" "frontend/app/(workspace)/pnl/page.tsx"
git commit -m "M9: P&L page with equity curve and mode toggle"
```

---

## Task 7: `/upload` 页 + 上传表单

**Files:**
- Create: `frontend/app/(workspace)/_components/UploadForm.tsx`
- Modify: `frontend/app/(workspace)/upload/page.tsx`

- [ ] **Step 1: 创建 `UploadForm.tsx`(client component)**

文件选择 + 拖放区;提交调 `api.uploadStatement(file)`;渲染 `UploadReport`(每账户四类计数);400 错误行内显示。

```tsx
"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { api, type UploadReport } from "@/lib/api";
import { IconUpload } from "./icons";

function CountRow({
  label,
  added,
  skipped,
}: {
  label: string;
  added: number;
  skipped: number;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted">{label}</span>
      <span className="tabular">
        <span className="text-up">+{added}</span>
        <span className="ml-2 text-muted">{skipped} skipped</span>
      </span>
    </div>
  );
}

/**
 * IBKR Flex CSV 上传表单。纯本地导入(不联网);成功后展示每账户的
 * 导入计数,并引导去 Positions 刷新行情。
 */
export function UploadForm() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<UploadReport | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await api.uploadStatement(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) setFile(f);
        }}
        className={`flex flex-col items-center gap-3 rounded-2xl border border-dashed p-12 text-center transition-colors ${
          dragOver ? "border-accent bg-accent-soft" : "border-border bg-surface/40"
        }`}
      >
        <IconUpload width={32} height={32} className="text-accent" />
        <p className="text-sm text-muted-strong">
          拖放 IBKR Flex CSV 到这里,或
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium hover:border-accent hover:text-accent"
        >
          选择文件
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {file && (
          <p className="tabular text-xs text-muted">{file.name}</p>
        )}
      </div>

      <button
        type="button"
        onClick={submit}
        disabled={!file || busy}
        className="rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-rail-deep transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "导入中…" : "导入对账单"}
      </button>

      {error && (
        <p className="rounded-xl border border-down/40 bg-down/10 px-4 py-3 text-sm text-down">
          {error}
        </p>
      )}

      {report && (
        <div className="space-y-4">
          <p className="text-sm font-medium text-up">导入完成。</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {report.accounts.map((a) => (
              <div
                key={a.broker_account_id}
                className="space-y-2 rounded-2xl border border-border bg-surface/60 p-5"
              >
                <p className="font-medium text-foreground">
                  {a.broker_account_id}
                </p>
                <CountRow label="Instruments" {...a.instruments} />
                <CountRow label="Trades" {...a.trades} />
                <CountRow label="Cash flows" {...a.cash_flows} />
                <CountRow label="Corporate actions" {...a.corporate_actions} />
              </div>
            ))}
          </div>
          {report.accounts[0] && (
            <Link
              href={`/positions?account=${encodeURIComponent(
                report.accounts[0].broker_account_id,
              )}`}
              className="inline-block text-sm font-medium text-accent hover:underline"
            >
              去 Positions 刷新行情 →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 重写 `upload/page.tsx`**

```tsx
import { IconUpload } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { UploadForm } from "../_components/UploadForm";

export default function UploadPage() {
  return (
    <PageShell
      group="Activity"
      title="Upload Statements"
      subtitle="导入 IBKR Flex Query CSV —— 解析成交、现金流、公司行动。重复导入按 ID 幂等。"
      icon={IconUpload}
    >
      <UploadForm />
    </PageShell>
  );
}
```

- [ ] **Step 3: 验证**

Run: `cd frontend && npm run build && npm run lint`
Expected: build 成功、lint 无错。

- [ ] **Step 4: Commit**

```bash
git add "frontend/app/(workspace)/_components/UploadForm.tsx" "frontend/app/(workspace)/upload/page.tsx"
git commit -m "M9: upload page with statement import form"
```

---

## 收尾

所有任务完成后,派最终整体审查 subagent,然后用 superpowers:finishing-a-development-branch 收口(合并回 `main`)。

**验证清单:**
- [ ] `cd frontend && npm run build` 通过。
- [ ] `cd frontend && npm run lint` 无错。
- [ ] `make dev` 起后端 + 前端,人工冒烟:`/upload` 能选文件;`/positions` `/trades` `/pnl` 在后端离线/无账户时显示空态而非崩溃;账户栏从 `GET /accounts` 渲染;点账户 pill 改 URL `?account=`;「刷新行情」按钮带图标。
- [ ] 后端 160 测试仍通过(M9 不动后端,确认无意外改动)。

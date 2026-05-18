# M9 — 前端页面 (Frontend Pages) 设计

> Phase 1 收尾里程碑。把占位页换成真页面,消费 M8 的 HTTP API。

## 目标

让用户能在浏览器里完成「导入对账单 → 看持仓/成交/盈亏 → 刷新行情」的完整闭环,
复用现有的 Discord 三栏壳与 TradingView 暗色 + Robinhood 设计语言。

## 范围

**做:**
- `/upload` — 上传 IBKR Flex CSV,显示导入报告。
- `/positions` — 持仓表 + 「刷新行情」按钮(带「更新行情」图标)。
- `/trades` — 成交流水表。
- `/pnl` — 已实现盈亏摘要 + 净值曲线图 + Mode A/B 切换。
- 账户栏(`AccountRail`)改成 `GET /accounts` 动态驱动。
- 选中账户用 URL search param `?account=<broker_account_id>` 在 workspace 内共享。
- `lib/api.ts` 加 typed endpoints。
- 引入 Recharts 作图表库。

**不做(YAGNI):**
- `/holdings` `/orders` `/performance` `/tax` `/ai` `/news` `/settings/*` —— 保持占位。
- `Aggregate`(多账户合并)视图 —— Phase 2。
- 成交表分页/筛选 —— 一次性渲染,表格自身滚动。
- 前端单元测试框架 —— 见「测试策略」。

## 已定决策

1. **图表库 = Recharts**(轻量、声明式、React 19 兼容)。项目此前无图表库。
2. **账户状态 = URL search param `?account=<broker_account_id>`**。刷新安全、可分享、
   服务端组件可直接读。不引入 React context。
3. **`{account_id}` 路径参数 = `broker_account_id`**(与 M8 一致)。

## 技术约束

- Next.js **16.2.4** App Router + React 19.2 + Tailwind v4。
- Next.js 15+ 破坏性变更:服务端组件的 `params` / `searchParams` 是 **Promise**,
  必须 `await`。页面签名:`async function Page({ searchParams }: { searchParams: Promise<{...}> })`。
- 数据页用服务端组件 + `export const dynamic = "force-dynamic"`(同 `dashboard/page.tsx`)。
- 交互件(账户切换、刷新按钮、上传表单、Mode 切换)是 `"use client"` 孤岛。
- **Decimal 序列化**:Pydantic v2 默认把 `Decimal` 序列化成 JSON **字符串**。
  前端数值字段类型按 `string` 处理,渲染前用 `toNum()` 辅助函数转 `number`。
  (`Number("1.5") === 1.5`,对数字输入也安全,故此选择两头兼容。)

## 架构

### 数据流

```
workspace/layout.tsx (server)
  └─ GET /accounts ──> Sidebar(accounts) (client)
                         ├─ AccountRail —— 渲染账户 pill,点击 → router.push(?account=id)
                         └─ ModuleRail  —— 导航,链接保留当前 ?account

page.tsx (server, async)
  ├─ await searchParams → account = searchParams.account ?? accounts[0]
  ├─ GET /accounts/{account}/positions | trades | pnl | curve
  └─ 渲染表格/图表 + 交互孤岛
```

### `lib/api.ts`

新增 `apiPost` / `apiPostForm` 与 typed 模型 + `api` 方法:

```ts
export type Account = {
  broker_account_id: string; name: string;
  base_currency: string; broker: string;
};
// Decimal 字段一律 string;辅助 toNum() 转数字。
export type Position = {
  symbol: string; quantity: string; cost_basis: string; average_cost: string;
  market_price: string | null; market_value: string | null;
  unrealized_pnl: string | null;
};
export type Trade = {
  trade_id: string; symbol: string; side: string; quantity: string;
  price: string; proceeds_usd: string; commission_usd: string;
  realized_pnl_ibkr: string | null; executed_at: string;
};
export type Pnl = { realized_pnl: string; open_position_count: number; base_currency: string };
export type CurvePoint = { on_date: string; cumulative_pnl: string; pct: string | null };
export type AppendCount = { added: number; skipped: number };
export type AccountImport = {
  broker_account_id: string;
  instruments: AppendCount; trades: AppendCount;
  cash_flows: AppendCount; corporate_actions: AppendCount;
};
export type UploadReport = { accounts: AccountImport[] };
export type RefreshResult = { broker_account_id: string; snapshot_rows: number };

api.accounts()                          // GET /accounts
api.positions(id)                       // GET /accounts/{id}/positions
api.trades(id)                          // GET /accounts/{id}/trades
api.pnl(id)                             // GET /accounts/{id}/pnl
api.curve(id, mode)                     // GET /accounts/{id}/curve?mode=A|B
api.refreshPrices(id)                   // POST /accounts/{id}/refresh-prices
api.uploadStatement(file)               // POST /statements/upload (multipart)
```

`apiGet` 已有;新增 `apiPost<T>(path, body?)` 与 `apiPostForm<T>(path, FormData)`。
失败抛 `Error`,消息含状态码与后端 `detail`(用于上传 400 的人类可读报错)。

### 共享 UI(新建 `_components/`)

- `PageShell.tsx` —— 提炼出页头(group / title / subtitle / icon),`/upload` `/positions`
  `/trades` `/pnl` 与现有 `PlaceholderPage` 共用同一视觉。
- `DataTable.tsx` —— 轻量表格原语(`<Table>` `<Th>` `<Td>`),暗色描边、`tabular` 数字、
  斑马行;持仓/成交两页共用。
- `EmptyState.tsx` —— 无账户 / 无数据 / 后端离线的统一占位。
- `format.ts`(放 `lib/`)—— `toNum`、`fmtMoney`、`fmtNum`、`fmtPct`、`pnlClass`
  (正 `text-up` 负 `text-down`)。

### 交互孤岛(client components)

- `AccountRail`(改造)—— props 收真实 `Account[]` + `activeId`;点击 pill 调
  `useRouter().push(pathname + ?account=id)`。`short` 取 `broker_account_id` 末 4 位,
  `tint` 按索引从固定调色板取色。
- `RefreshPricesButton.tsx` —— 带 `IconRefresh`(新图标,环形箭头)的按钮,文案「刷新行情」。
  点击 → `api.refreshPrices(id)` → 成功后 `router.refresh()` 重取服务端数据;
  pending 态禁用 + 转圈;失败显示行内错误。
- `UploadForm.tsx` —— 文件选择 + 拖放区;提交 → `api.uploadStatement` → 渲染
  `UploadReport`(每账户四类 added/skipped);400 错误行内显示。
- `CurveModeToggle.tsx` —— A/B 段控件,改 `?mode=` search param。

### 新图标

`icons.tsx` 加 `IconRefresh` —— 环形双箭头,沿用 24×24 / stroke 1.6 风格。
用户明确要求「刷新行情」按钮要有「更新行情」图标。

## 各页面规格

### `/upload`
- 服务端壳 + `UploadForm` 客户端孤岛。
- 拖放区 + `<input type=file accept=".csv">`。单文件。
- 提交后报告:每个账户一张卡,列 instruments / trades / cash_flows / corporate_actions
  的 `+added / skipped`。
- 完成后提示「去 Positions 刷新行情」(链接到 `/positions?account=<第一个导入账户>`)。
- 后端 400(无法识别的文件)→ 行内红色错误。

### `/positions`
- `?account` 缺省取 `accounts[0]`。
- `DataTable`:Symbol / Qty / Avg Cost / Cost Basis / Mkt Price / Mkt Value / Unrealized P&L。
- `market_*` 为 `null`(期权或未刷新)→ 显示「—」。
- 未实现盈亏正绿负红。
- 页头右侧 `RefreshPricesButton`。
- 无持仓 → `EmptyState`(提示先上传 / 刷新)。

### `/trades`
- `DataTable`:Date / Symbol / Side / Qty / Price / Proceeds / Commission / Realized P&L(IBKR)。
- 后端已按 `executed_at` 倒序。Side 用色块(BUY 绿 / SELL 红)。
- `realized_pnl_ibkr` 为 `null` → 「—」。
- 一次性渲染全部行,表体区域 `overflow-y-auto`。

### `/pnl`
- 三张摘要卡:Realized P&L / Open Positions / Base Currency(复用 dashboard 的 `Metric` 风格)。
- 净值曲线:Recharts `AreaChart`,X=`on_date`,Y=`cumulative_pnl`;
  暗色网格、accent 描边、渐变填充、`tabular` tooltip。
- `CurveModeToggle`(A/B),改 `?mode=`,默认 B。
  - Mode A = IBKR/TWR;Mode B = 累计盈亏 ÷ 累计净入金。卡片下方一行小字注明当前口径。
- 曲线为空 → `EmptyState`。

## 错误与边界处理

- 所有服务端 `fetch` 包 try/catch;失败渲染 `EmptyState` 的「后端离线」变体(同
  `dashboard` 的 `getHealth` 容错)。
- 账户数为 0(全新 DB):`AccountRail` 只显示 Logo + Add;数据页显示「先去 Upload 导入」。
- `?account` 指向不存在的账户:后端返 404 → 页面按「后端离线/无数据」降级。

## 测试策略

前端目前**没有**单元测试框架(只有 eslint)。M9 不引入测试框架 —— 那是独立决策,
会膨胀范围;后端才是被测层(160 测试)。M9 每个任务的验证门 = 

1. `npm run build`(`next build` 通过 —— 类型检查 + 编译)。
2. `npm run lint`(eslint 通过)。
3. 必要时 `make dev` 起后端 + 前端做一次人工冒烟。

实施计划里每个任务以 build + lint 作为通过判据,而非单元测试。

## 文件清单

**新建:**
- `frontend/lib/format.ts`
- `frontend/app/(workspace)/_components/PageShell.tsx`
- `frontend/app/(workspace)/_components/DataTable.tsx`
- `frontend/app/(workspace)/_components/EmptyState.tsx`
- `frontend/app/(workspace)/_components/RefreshPricesButton.tsx`
- `frontend/app/(workspace)/_components/UploadForm.tsx`
- `frontend/app/(workspace)/_components/CurveModeToggle.tsx`
- `frontend/app/(workspace)/_components/EquityCurve.tsx`(Recharts 包装)

**修改:**
- `frontend/package.json` —— 加 `recharts`。
- `frontend/lib/api.ts` —— 加 typed endpoints + `apiPost`/`apiPostForm`。
- `frontend/app/(workspace)/_components/icons.tsx` —— 加 `IconRefresh`。
- `frontend/app/(workspace)/_components/AccountRail.tsx` —— 收真实账户 + URL 导航。
- `frontend/app/(workspace)/_components/ModuleRail.tsx` —— 链接保留 `?account`。
- `frontend/app/(workspace)/_components/Sidebar.tsx` —— 收 `accounts` prop,去掉本地状态。
- `frontend/app/(workspace)/layout.tsx` —— 服务端取 `GET /accounts` 传给 `Sidebar`。
- `frontend/app/(workspace)/upload/page.tsx`
- `frontend/app/(workspace)/positions/page.tsx`
- `frontend/app/(workspace)/trades/page.tsx`
- `frontend/app/(workspace)/pnl/page.tsx`
- `frontend/app/(workspace)/_config/workspace.ts` —— `accounts` 静态常量可删/留作色板。

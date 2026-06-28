# Phase 2 · Milestone A — 实时轮询(Yahoo 前端拉)设计

> Phase 2 第一步。Phase 1 的"按按钮才刷新"换成"前端定时拉 Yahoo,持仓 + P&L 曲线尾部自动更新"。为 Phase 2 · Milestone B(IBKR Client Portal 实时)铺路径,但不引入后端调度、不引入实时推送。

## 目标

让用户打开 `/positions` 或 `/pnl` 时,**不点按钮**也能看到行情更新:
- `/positions` 持仓表的 `市价 / 市值 / 未实现盈亏` 三列定时跳动。
- `/pnl` 的净值曲线**最后一点**(以及右上角累计 pct)跟着今天的实时市值走。
- 用户可调节频率;盘外默认不打扰;失败时明确告知"行情不可用"。

## 范围

**做:**
- 新后端接口 `GET /accounts/{id}/live-snapshot?mode=A|B` —— 纯读、无 DB 写,返回 live positions + 重算的 curve 尾部。
- `MarketDataProvider` 接口加 `get_latest_closes(symbols)` 批量方法;`YahooFinanceProvider` 用 `yfinance.download(...)` 单次拉多 symbol 实现。
- 前端通用 `useLivePolling` hook(共享给 /positions 与 /pnl)。
- `/positions` 与 `/pnl` 页面加 live 行为(SSR 初始值保持不变,客户端孤岛接管轮询)。
- `/settings` 页面替换 PlaceholderPage,提供"频率"与"包含盘外"两项设置,存浏览器 localStorage。
- 状态徽章组件 `LiveStatusBadge`:`Live · 23s 前` / `Market closed` / `Manual` / `行情不可用`。

**不做(YAGNI / 留给后续):**
- ❌ `/dashboard` 自动刷新 —— 当前 dashboard 的 `Total Value` / `Day P&L` 还是占位 `—`,没有"活数字"可刷;等独立的"Dashboard 真值"里程碑把它接上数据后,直接订阅同一个轮询源即可。
- ❌ 后端定时器 / scheduler / 多账户后台并行轮询 —— 留给 Milestone B(IBKR 接通后才有真正的全后台价值)。
- ❌ Server-Sent Events / WebSocket 推送 —— 同上。
- ❌ NYSE 假日日历 —— Mon–Fri 即视为开盘,假日轮询会拉到 stale 价(可接受;徽章不会标记)。
- ❌ Pre-market / After-hours 分窗口 —— 只一个"包含盘外"总开关。
- ❌ 价格变化的闪烁动画(用户已确认要克制金融风格,不闪)。
- ❌ 单格 stale 标记 —— strict 模式整体 fail,无逐格降级。
- ❌ 跨页面共享轮询 Context —— /positions 与 /pnl 各自独立轮询;切页瞬间多一次 fetch 是可接受代价。Context 复用留给 Milestone B(三页共订阅时才有意义)。
- ❌ Settings 同步多浏览器 —— localStorage 即可,单用户本地。

## 已定决策

1. **接口形状 = 单一伞形 `GET /accounts/{id}/live-snapshot`**(候选 X = 两个独立接口,Z = 前端聚合)。理由:同一个轮询周期里两个页面共享一次后端调用 + 一次 Yahoo 调用;曲线 Mode A/B 数学只在后端一份。
2. **失败模式 = strict**(任一 symbol 缺即整体 503)。理由:用户希望明确显示"行情不可用"而非逐格降级,避免用户误以为"那行价是真的没动"。
3. **市场时段 + 设置 = 全前端**(候选 B = 混合)。理由:Milestone A 只有一个浏览器客户端在调用 live 接口,后端节流闸门在这一阶段不创造价值;接 IBKR 时反正后端聚合层要重写,届时再在后端放市场时段逻辑。
4. **轮询频率 = 用户可配置**(默认 60s,候选 30s / 60s / 120s / 手动)。理由:Yahoo 延迟 15–20 分钟限制了"刷得多快"的天花板,但默认 60s 仍能让 UI 的"X 秒前"反馈活;后续接 IBKR 时同一设置可复用。
5. **轮询调度 = 前端独立 per page**(候选:layout 级 Context 共享)。理由:简单优先;切页瞬间多一次 fetch 是小代价。
6. **设置存储 = localStorage**(候选:后端 user_settings 表)。理由:单用户本地应用,无登录态;后端表只在多设备/多用户出现时才有必要。
7. **后端无 DB 写**。`live-snapshot` 不写 `positions_snapshot`;snapshot 表仍由用户点"刷新行情"按钮(走老的 `refresh-prices` → `rebuild_snapshots` 全量重建)冷启动。
8. **盘外默认暂停**;Settings 里的"包含盘外"开关让用户启用。盘外打开时,徽章仍标 `Live`(因为前端在轮询)而非 `Market closed`。**该开关只影响 weekday 的 09:30 ET 前 / 16:00 ET 后**;周六周日始终视为 `Market closed`(无盘可言),不轮询。

## 技术约束

- **延迟来源**:Yahoo Finance via `yfinance`,约 15–20 分钟延迟,免费、无 key。
- **批量拉取**:`yfinance.download(tickers="AAPL TSLA NVDA", period="5d", auto_adjust=True, group_by="ticker")`,一次 HTTP 拿多 symbol,远比 N 次 `Ticker.history(...)` 高效。沿用现有 `history_fn` 可注入模式做离线测试。
- **市场时段(前端)**:`Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York' })` 拿 ET 小时/分/星期,Mon–Fri 09:30–16:00 视为开盘。无假日检查。
- **`document.hidden` + `visibilitychange`**:tab 切走时跳过 tick;通过监听 `visibilitychange`,切回可见时立即触发一次额外 tick(不等下一个 interval)。
- **Decimal 序列化**:沿用 M9 的约定 —— 后端 Pydantic 把 `Decimal` 序列化成 JSON 字符串,前端用 `toNum()` 转。
- **SSR 不变**:`/positions` 与 `/pnl` 的 SSR 路径继续读 snapshot 表,首屏数据来自上次 `refresh-prices`;hydration 后客户端孤岛接管 live。F5 后首屏会闪一下旧价 —— 已接受。

## 架构

### 数据流

```
                ┌────────────────────────────────────────────────────────┐
                │  Browser                                               │
                │                                                        │
                │  /settings page                                        │
                │   └─ <LiveDataSettings>                                │
                │      └─ getLiveSettings() / setLiveSettings()          │
                │         └─ localStorage: { intervalSeconds, after }    │
                │                                                        │
                │  /positions page                                       │
                │   ├─ SSR: GET /positions  (snapshot 旧价)              │
                │   └─ <LivePositionsTable initial={...} accountId={..}> │
                │      └─ useLivePolling(fetcher, onData)                │
                │         ├─ isUsMarketOpen(now) + AH 开关 → 判定        │
                │         ├─ document.hidden → pause                     │
                │         └─ tick → api.liveSnapshot(accountId, "B")     │
                │            └─ setPositions(res.positions)              │
                │                                                        │
                │  /pnl page                                             │
                │   ├─ SSR: GET /pnl + /curve  (snapshot 旧价)           │
                │   └─ <LivePnlTail initial={{ curve, mode }} ...>       │
                │      └─ useLivePolling(fetcher, onData)                │
                │         └─ tick → api.liveSnapshot(accountId, mode)    │
                │            └─ replaceOrAppendLast(curve, res.curve_tail)│
                │               + setPct(res.curve_tail.pct)             │
                └────────────────────────────────────────────────────────┘
                                  │
                                  │ GET /accounts/{id}/live-snapshot?mode=A|B
                                  ▼
                ┌────────────────────────────────────────────────────────┐
                │  Backend (FastAPI)                                     │
                │                                                        │
                │   compute_positions(db, account)                       │
                │   symbols = priced positions' symbols                  │
                │   closes = provider.get_latest_closes(symbols)         │
                │   ├─ raise → 503 "行情不可用"                          │
                │   └─ any missing → 503 "行情不可用: AAPL, MSFT"        │
                │   live_positions = overlay marks                       │
                │   live_holdings_usd = sum(live market values)          │
                │   cash_today = compute_cash_at(account, today)         │
                │   day_points = build_day_points(...)                   │
                │   replace_or_append_last(day_points,                   │
                │       DayPoint(today, cash_today + live_holdings, 0))  │
                │   curve = compute_equity_curve(day_points, mode)       │
                │   return { fetched_at, positions, curve_tail = last }  │
                └────────────────────────────────────────────────────────┘
```

### 关键不变量

- **后端零 DB 写**:`live-snapshot` 是纯读接口;snapshot 表只由 `refresh-prices` 按钮触发写入。
- **市场时段判定不在后端**:后端不知道 ET 是几点,被调到了就老老实实去拉 Yahoo。前端是唯一的节流闸门。
- **单一真相源**:`/positions` 与 `/pnl` 的 live 数据来自同一个端点同一次调用 —— 即便两页独立轮询,各自周期里也只查一次 Yahoo。
- **strict 失败语义**:任一 symbol 缺失即整体 503,前端表格保留上一次 live 成功的数据(或 SSR 初值)+ 徽章红字"行情不可用"。

## 后端

### 文件改动

| 文件 | 变更 |
|---|---|
| `app/services/providers/base.py` | 接口加抽象方法 `get_latest_closes(symbols: list[str]) -> dict[str, Decimal]` |
| `app/services/providers/yahoo.py` | 实现 `get_latest_closes`,用 `yfinance.download(...)` 单次请求拉多 symbol。沿用 `history_fn` 可注入模式;新增 `closes_fn` 钩子做批量离线测试 |
| `app/services/snapshot/cash.py`(**新**) | `compute_cash_at(session, account, day) -> Decimal` —— 把 `build_day_points` 里那段"算到某天的累计现金"抽出来,`live-snapshot` 复用;`build_day_points` 改成 import 它 |
| `app/services/snapshot/live.py`(**新**) | `compute_live_snapshot(session, account, provider, mode) -> LiveSnapshot` —— 上面伪代码描述的整段逻辑。命名空间放 `snapshot/` 下与 `builder.py` 并列 |
| `app/api/schemas.py` | 新增 `CurveTailOut`、`LiveSnapshotOut` |
| `app/api/accounts.py` | 新增 `GET /accounts/{id}/live-snapshot`,挂在已有 router 上,沿用 `get_account` + `get_market_data_provider` 依赖 |

### 接口契约

```http
GET /accounts/{account_id}/live-snapshot?mode=B
```

成功响应(200):
```json
{
  "fetched_at": "2026-06-27T13:42:11Z",
  "positions": [ /* PositionOut[] —— 同 /positions,marks 已套 live */ ],
  "curve_tail": {
    "on_date": "2026-06-27",
    "cumulative_pnl": "12345.67",
    "pct": "0.0823"
  }
}
```

失败响应:
- `503 { "detail": "行情不可用: AAPL, MSFT" }` —— 任一 symbol 缺失或 provider 抛
- `404 { "detail": "Account not found" }` —— 沿用 `get_account` 依赖

### 测试

- `test_yahoo_batch_latest_happy` —— 注入 `closes_fn`,验证返回 dict 形状(已知 symbol → Decimal)
- `test_yahoo_batch_latest_missing` —— `closes_fn` 返回缺一个 symbol,验证 dict 不含它(由调用方判 strict)
- `test_live_snapshot_happy` —— 4 个开仓 STOCK,provider 注入 4 个价 → 200,positions 的 marks 已套上,`curve_tail.on_date == date.today()`
- `test_live_snapshot_strict_partial_missing` —— provider 注入 3 个价缺 1 个 → 503,detail 含缺失 symbol
- `test_live_snapshot_provider_exception` —— provider 抛 → 503
- `test_live_snapshot_options_passthrough` —— OPTION 仓位无 Yahoo 价,不算缺失;它的 PositionOut 仍 mark=None(同现有 /positions 语义),不参与 holdings_usd 求和
- `test_live_snapshot_mode_a_vs_b` —— 同数据 mode=A 与 mode=B 算出来的 pct 不同
- `test_live_snapshot_no_positions` —— 空账户 → 200,positions=[],curve_tail 取最后一个 day_point(可能是入金日)或 fall back
- `test_compute_cash_at_matches_build_day_points` —— 同一天的 `compute_cash_at(day)` 等于 `build_day_points` 最后那个 DayPoint 里隐含的 cash

## 前端

### 文件改动

**新文件:**

| 文件 | 职责 |
|---|---|
| `lib/settings.ts` | `getLiveSettings()` / `setLiveSettings(partial)` / `subscribeLiveSettings(callback)`。读写 `localStorage["liveDataSettings"]`。Schema: `{ intervalSeconds: 30 \| 60 \| 120 \| null, includeAfterHours: boolean }`,默认 `{ intervalSeconds: 60, includeAfterHours: false }`,`intervalSeconds = null` 视为"手动" |
| `lib/market-hours.ts` | `isUsMarketOpen(now: Date): boolean` —— `Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday, hour, minute, hour12: false })` 取 weekday + hour:minute;Mon–Fri 且 09:30 ≤ ET < 16:00 |
| `lib/hooks/useLivePolling.ts` | 通用 hook:`useLivePolling<T>({ fetcher, onData })`。内部维护 `status` / `lastFetchedAt`,执行调度(读 settings、判市场时段、`document.hidden`、`setInterval`、监听 `visibilitychange` 切回时立即触发一次、cleanup),把数据交给 `onData` 回调让消费者自行处理 |
| `app/(workspace)/_components/LiveStatusBadge.tsx` | 接收 `{ status, lastFetchedAt }`,渲染 dot + 文案。变体:`Live · 23s 前`(绿点)/ `Market closed`(灰点)/ `Manual`(灰点)/ `行情不可用`(红点)。每秒重算 "X 秒前" 字符串 |
| `app/(workspace)/positions/_components/LivePositionsTable.tsx` | `"use client"`,接收 SSR `initial: Position[]` 与 `accountId`,内部 `useLivePolling` + 渲染 DataTable + 右上角放 `LiveStatusBadge` |
| `app/(workspace)/pnl/_components/LivePnlTail.tsx` | `"use client"`,接收 SSR `initial: { curve: CurvePoint[], pct: Decimal }` + `accountId` + `mode`,渲染 EquityCurve + 右上角 pct + 状态徽章;每次 tick 用 `replaceOrAppendLast(curve, curve_tail)` 更新曲线 |
| `app/(workspace)/settings/_components/LiveDataSettings.tsx` | `"use client"`,radio(频率 30/60/120/Manual)+ checkbox(包含盘外)+ "保存" 按钮。保存写 localStorage 并触发 `storage` 事件让其它 tab 同步 |

**改动文件:**

| 文件 | 变更 |
|---|---|
| `lib/api.ts` | 加 `api.liveSnapshot(accountId, mode)`;`LiveSnapshot` 类型导出 |
| `app/(workspace)/positions/page.tsx` | 表格部分换成 `<LivePositionsTable initial={positions} accountId={accountId} />`;`RefreshPricesButton` 保留(它仍是冷启动重建 snapshot 的入口) |
| `app/(workspace)/pnl/page.tsx` | 曲线 + 右上角 pct 部分换成 `<LivePnlTail initial={{ curve, pct: curve[curve.length-1].pct }} accountId={accountId} mode={mode} />` |
| `app/(workspace)/settings/page.tsx` | PlaceholderPage 替换为 `<LiveDataSettings />` |

### 设置 UI 草图(/settings)

```
┌─ Live Data ────────────────────────────────────────┐
│                                                    │
│  Polling frequency                                 │
│   ( ) 30s — 反馈最活,Yahoo 调用最频              │
│   (•) 60s — 默认                                  │
│   ( ) 120s — 省网络                               │
│   ( ) Manual — 不自动刷新                         │
│                                                    │
│  ☐ Include after-hours / pre-market               │
│    默认关闭。打开后,周一至周五全天轮询。         │
│                                                    │
│              [取消]  [保存]                        │
└────────────────────────────────────────────────────┘
```

### 状态机(`useLivePolling`)

```
              ┌──────────┐
              │   idle   │  初始,settings 未读取或 accountId 未定
              └────┬─────┘
                   │ 读 settings → intervalSeconds=null
                   ▼
              ┌──────────┐
              │  manual  │  不调度,只显示初始数据
              └──────────┘

              ┌──────────┐
              │ polling  │  正在 fetch
              └────┬─────┘
                   │ 200
                   ▼
              ┌──────────┐
              │   live   │  上次成功 +N 秒,等待下一 tick
              └────┬─────┘
                   │ tick & (盘外 & !AH) → market-closed
                   │ tick & document.hidden → 跳过这次,保持 live
                   │ tick & 503/网络错 → unavailable
                   ▼
              ┌──────────────┐  ┌──────────────┐
              │market-closed │  │ unavailable  │  徽章红;表格保留上次数据
              └──────────────┘  └──────────────┘
```

### 测试策略

- 前端无单元测试框架(沿用 M9 决定)。
- **手动冒烟清单**(放进 plan):
  1. 打开 /positions(localhost,非 127.0.0.1)→ 60s 后看到价格更新;徽章从 `Live · 0s 前` 走到 `Live · 60s 前`
  2. 切到别的 tab 1 分钟,切回 → 不应等满 60s,应立即触发一次
  3. 改 settings 为 30s → 回 /positions,频率改变
  4. 改 settings 为 Manual → /positions 不再自动刷新,徽章 `Manual`
  5. 改 settings 关闭盘外 + 当前是非市场时段 → 徽章 `Market closed`,不发请求(DevTools 网络面板可验)
  6. 开盘外 → 徽章 `Live`,正常轮询
  7. 后端杀掉 → 徽章 `行情不可用`(红),表格仍显示上次数据
  8. /pnl 页面:曲线最后一点会跳动,右上角 pct 跟着变
  9. 同时打开 /positions 和 /pnl(两个 tab)→ 两边都轮询,不互相干扰

## 实施步骤(高层)

按依赖顺序拆任务,具体颗粒度交给 writing-plans:

1. 后端 `get_latest_closes` 接口 + Yahoo 批量实现 + 测试
2. 后端 `compute_cash_at` 抽取 + 测试
3. 后端 `compute_live_snapshot` + 测试
4. 后端 `/live-snapshot` 端点 + 集成测试
5. 前端 `lib/settings.ts` + `lib/market-hours.ts` + `useLivePolling` 通用 hook
6. 前端 `LiveStatusBadge` + `api.liveSnapshot` 客户端
7. 前端 `LivePositionsTable` 接入 + /positions/page.tsx 改动
8. 前端 `LivePnlTail` 接入 + /pnl/page.tsx 改动
9. 前端 `/settings` 页面 + `LiveDataSettings` 表单
10. 浏览器手动冒烟(上方 9 条清单) + 合并

## 验收

- 后端 pytest 全绿(`make test`),新测试覆盖上方 9 条
- `make lint` 全绿
- `next build` 全绿
- 手动冒烟 9 条全过
- README "进度" 段加 Phase 2 · Milestone A 条目;`MEMORY.md` 状态更新

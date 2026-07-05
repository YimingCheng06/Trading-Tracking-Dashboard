# Phase 2 · Milestone B — IBKR Client Portal 实时报价设计

> Phase 2 第二步。Milestone A 的 Yahoo 轮询(15–20 分钟延迟)升级为 IBKR Client
> Portal Gateway 真实时报价,Gateway 不在线时自动回落 Yahoo。同时把期权从
> "永远按成本计"升级为"IBKR 在线时按实时 mark 计价"。持仓对账、订单状态、
> 后台调度均**不在**本里程碑。

## 目标

用户本机跑起 IBKR CP Gateway 并登录后,`/positions` 与 `/pnl` 的轮询数据自动
变成真实时:

- 股票/ETF 的 `市价 / 市值 / 未实现盈亏` 来自 IBKR 实时报价(而非 Yahoo 延迟价)。
- 期权持仓的市值/未实现盈亏用 IBKR **mark price** 实时计算(此前永远按成本计)。
- 徽章显示数据来源:`Live · IBKR`(真实时)/ `Live · Yahoo (delayed)`(回落态)。
- Gateway 没开、没登录、会话过期 → **静默**回落 Yahoo,功能永不中断,期权回落成本价。

## 范围

**做:**

- `gateway/` 目录(gitignored)+ `make gateway` 启动命令 + README 配置文档
  (下载、Java 依赖、启录流程)。
- `app/services/providers/ibkr_cp.py`:`IBKRClientPortalClient`(薄 HTTP 封装,
  可注入)+ `IBKRClientPortalProvider`(实现 `MarketDataProvider` 的 live 路径)。
- `ChainedMarketDataProvider`:每请求探测 IBKR auth → 在线用 IBKR(Yahoo 补洞),
  离线整体走 Yahoo。
- 期权 conid 两步解析 + mark price 取价 + `compute_live_snapshot` 期权实时市值分支。
- `live-snapshot` 响应加 `source: "ibkr" | "yahoo"`;前端徽章显示来源。
- `Settings` 加 `ibkr_gateway_url`(默认 `https://localhost:5000/v1/api`)。

**不做(YAGNI / 留给后续):**

- ❌ 实时持仓对账(IBKR 报的持仓 vs 本地账本持仓)—— 下一个里程碑。
- ❌ 订单状态页面 —— 再下一个里程碑。
- ❌ 后台保活任务(`/tickle` 定时器)/ 后端 scheduler —— 方案 2 已排除;
  session 频繁掉线再加,加时不改本里程碑任何接口。
- ❌ Gateway 自动下载 / 自动登录 —— 2FA 无法自动化,登录永远是用户手动动作。
- ❌ 历史日线走 IBKR —— `refresh-prices` / 快照重建 / 净值曲线历史段继续用
  Yahoo,`IBKRClientPortalProvider.get_daily_closes` 不实现。
- ❌ WebSocket 流式报价 —— CP Gateway 支持 ws,但轮询模型(Milestone A 的
  `useLivePolling`)完全够用,前端零结构改动是本里程碑的卖点。
- ❌ 新设置项 —— 回退全自动,`/settings/preferences` 不动。
- ❌ 跨页共享轮询 Context —— 维持 Milestone A 决定,各页独立轮询。

## 已定决策

1. **范围 = 只做实时报价**(候选:+持仓对账 / 全量含订单)。理由:报价是
   Milestone A 管线的直接升级,前端几乎不动;持仓对账和订单页各自值得独立设计。
2. **Gateway 掉线 = 静默回退 + 来源徽章**(候选:显式警告提示重连)。理由:
   Gateway 不在线是常态(手动启动 + 2FA + 会话超时),日常快速看一眼不该被
   "IBKR 未连接"轰炸;来源徽章足以让用户知道数据是延迟的。
3. **期权实时定价 = 包含,但仅 IBKR 在线时**。IBKR 在线 → 期权查实时 mark;
   离线 → 期权按成本计(现状)。股票/ETF 任何时候都有价(IBKR 或 Yahoo)。
4. **架构 = 链式 Provider,每请求探测**(候选:后台 tickle 保活 / 前端直连
   Gateway)。理由:无常驻任务、无状态、好测试;探测是 localhost 调用开销可
   忽略;前端直连违背 provider 适配器在后端的锁定架构且有自签证书/CORS 死结。
5. **失败语义分层**:股票/ETF 维持 Milestone A 的 strict(补洞后仍缺 → 503);
   期权 best-effort(单个期权缺价 → 该期权回落成本价,不 503)。理由:流动性
   差的期权腿拿不到报价是常态,不该废掉整个快照;股票缺价则是异常,应显式报错。
6. **`source` 以 Gateway auth 为准**:authenticated → `"ibkr"`(即使个别
   symbol 由 Yahoo 补洞),否则 `"yahoo"`。理由:徽章表达的是"当前数据链路
   处于哪个档位",逐 symbol 标注来源是过度设计。
7. **TLS 校验对 Gateway 关闭**:Gateway 用自签名证书,后端 httpx 对
   `ibkr_gateway_url` 关闭 verify。仅 localhost 流量,可接受。
8. **conid 缓存 = 进程内 dict,无过期**。conid 是 IBKR 的永久合约 ID,不会变;
   后端重启即清空,足够。
9. **conid 来源 = DB 优先**(实现前勘察加入):Flex 导入的 instrument 自带
   conid,直接读 `Instrument.conid`;股票缺失才走 search API,期权缺失直接
   成本计。期权的两步 secdef 查询链路整个砍掉。
10. **顺手修 Milestone A live 尾点漏计期权成本价值的 bug**(见 live.py 组件节)。
    离线回落路径的"现状行为"指修复后的口径:期权始终按成本进尾点。

## 技术约束(CP Gateway API)

- **Gateway**:IBKR 官方 `clientportal.gw`(Java 8+),`bin/run.sh root/conf.yaml`
  启动,监听 `https://localhost:5000`,REST 基路径 `/v1/api`。用户浏览器访问
  `https://localhost:5000` 登录(IBKR 账号 + 2FA),之后 Gateway 持有会话。
- **auth 探测**:`POST /iserver/auth/status` → `{authenticated: bool, ...}`。
  连接被拒 / 超时 / `authenticated: false` 都视为"IBKR 不在线"。超时设短
  (~2s),不拖慢回落路径。
- **会话预热**:每个后端进程生命周期内,首次用 snapshot 前调一次
  `GET /iserver/accounts`(IBKR 已知怪癖:不预热则 snapshot 返回空)。
- **conid 来源 = DB 优先**(实现前勘察发现的简化):IBKR Flex 导入的每个
  instrument(股票和期权)本来就带 IBKR `Conid` 列,已存进 `Instrument.conid`。
  所以 conid 解析**首选直接读 DB 字段**:
  - 股票/ETF:DB conid 缺失时(如公司行动建的 stub instrument)才退回
    `GET /iserver/secdef/search?symbol=X` → 取 `secType=STK` 第一条,结果
    进程内缓存;仍解析不到 → 该 symbol 走 Yahoo 补洞。
  - 期权:**只用 DB conid**(Flex 导入的期权必带 conid);缺失则该期权按
    成本计,不走 search(期权两步查询链路整个砍掉,YAGNI)。
- **快照取价**:`GET /iserver/marketdata/snapshot?conids=...&fields=31,7635`。
  字段 31 = last price,7635 = mark price。首次调用可能返回不含价格字段的
  部分响应 → 自动重试一次。价格值可能带状态前缀字母(如 `C` 前收、`H` 停牌)
  → 解析时剥掉前导字母再转 Decimal。
- **实施注**:以上端点/字段号以实现时对真 Gateway 的实测为准;若实测与此处
  记载不符,以实测修正 spec。
- **市场数据订阅**:用户 IBKR 账户若无实时行情订阅,IBKR 返回延迟价 —— 系统
  行为不变(照常显示,来源仍标 IBKR),不做订阅状态检测。

## 架构

### 数据流

```
Browser(不变: useLivePolling → api.liveSnapshot)
   │  GET /accounts/{id}/live-snapshot?mode=A|B
   ▼
Backend  live-snapshot endpoint
   │
   ▼
compute_live_snapshot(session, account, provider, mode)
   │  从 instruments 组装: equity = {symbol: conid|None}(股票/ETF)
   │                       options = {symbol: conid}(期权,DB conid 非空)
   ▼
ChainedMarketDataProvider.get_live_quotes(equity, options)
   ├─ ibkr.auth_ok()?  ── POST /iserver/auth/status (timeout 2s)
   │
   ├─ 在线(authenticated),IBKR 段任何异常 → 落到离线分支:
   │    symbol_conids = resolve_equity_conids(equity)   # DB conid 直用,缺的 search
   │    closes = ibkr.get_equity_closes(symbol_conids)  # snapshot 字段 31
   │    缺的 symbol → yahoo.get_latest_closes(missing) 补洞
   │    option_marks = ibkr.get_option_marks(options)   # 字段 7635 优先, 31 兜底
   │    单个期权缺 mark → 该期权不进 option_marks(成本计)
   │    source = "ibkr"
   │
   └─ 离线:
        closes = yahoo.get_latest_closes(equity 的 symbols)  # 现状,一字不变
        option_marks = {}                                     # 期权成本计
        source = "yahoo"
   │
   ▼
compute_live_snapshot 续:
   ├─ 股票/ETF: overlay closes;补洞后仍缺 → 503(strict, 同 Milestone A)
   ├─ 期权: symbol 在 option_marks → market_price = mark,
   │        market_value = mark × qty × multiplier,
   │        unrealized = market_value − cost_basis;
   │        不在 → market_* = None(展示同现状),尾点按 cost_basis 计入
   └─ 曲线尾点: live_holdings = 股票/ETF 实时市值 + 期权(mark 市值 或 cost_basis)
   │
   ▼
LiveSnapshot 响应 { source, positions, curve_tail }
   │
   ▼
LiveStatusBadge:  source=="ibkr" → "Live · IBKR"
                  source=="yahoo" → "Live · Yahoo (delayed)"
```

### 组件

**`app/services/providers/ibkr_cp.py`(新)**

- `IBKRClientPortalClient` —— 薄 HTTP 层,全部网络调用集中于此,构造时可注入
  transport(测试用 fake):
  - `auth_ok() -> bool` —— `/iserver/auth/status`,任何异常/超时/未认证 → False
  - `ensure_primed() -> None` —— 首次调用前打一次 `/iserver/accounts`(进程内标记)
  - `search_stock_conid(symbol) -> int | None`
  - `snapshot(conids, fields) -> dict[int, dict[str, str]]` —— 含一次自动重试
- `IBKRClientPortalProvider`(普通类,**不**继承 `MarketDataProvider` ——
  它不满足历史接口契约,只作为链式层的内部件):
  - `get_equity_closes(symbol_conids: dict[str, int]) -> dict[str, Decimal]`
    —— snapshot(字段 31)→ 剥前缀转 Decimal;无价的 symbol 缺席于结果
  - `resolve_equity_conids(equity: dict[str, int | None]) -> dict[str, int]`
    —— DB conid 直用;None 的走 search(带进程内缓存);解析不到的缺席
  - `get_option_marks(symbol_conids: dict[str, int]) -> dict[str, Decimal]`
    —— snapshot(字段 7635, 31);mark(7635)优先,缺退 last(31),再缺则缺席

**`ChainedMarketDataProvider(MarketDataProvider)`(新,`chain.py`)**

- 构造:`(ibkr: IBKRClientPortalProvider, yahoo: YahooFinanceProvider)`
- `get_live_quotes(equity, options) -> LiveQuotes(closes, option_marks, source)`
  —— live-snapshot 专用聚合入口;`equity: dict[symbol, conid|None]`、
  `options: dict[symbol, conid]`。IBKR 段任何异常 → 整体回落 Yahoo 路径
  (Gateway 在 auth 探测后、snapshot 前掉线的窗口)。
- `get_live_quotes` 在 `MarketDataProvider` 基类上有默认实现
  (`get_latest_closes` + 空 option_marks + `source="yahoo"`),所以现有测试
  的 fake provider 不用改;链式层覆写它。
- `get_daily_closes` / `get_latest_close` / `get_latest_closes` 直接转发
  Yahoo(`refresh-prices` 路径无感)。

**`app/services/snapshot/live.py`(改)**

- `compute_live_snapshot` 改调 `provider.get_live_quotes(equity, options)`
  (从 instruments 组装两个 dict:股票/ETF 全进 equity,期权带 conid 的进
  options)。期权 symbol 能匹配到 mark 时,market_value / unrealized_pnl 用
  `mark × qty × multiplier` 算;否则按成本。
- **顺手修 Milestone A 的尾点 bug**:历史日点(`build_day_points`)里期权按
  成本计入组合价值,但 live 尾点的 `live_holdings_usd` 此前只加股票/ETF ——
  期权价值在 live 尾点凭空消失,今天的点会比昨天低一块。修正:期权无 mark 时
  按 `cost_basis` 计入尾点(与历史日点口径一致),有 mark 时按实时市值计入。
- 响应 dataclass `LiveSnapshot` 加 `source` 字段。

**`app/api/`(改)**

- `deps.py`:`get_market_data_provider` 改为构造 `ChainedMarketDataProvider`
  (读 `settings.ibkr_gateway_url`)。
- `accounts.py`:live-snapshot 端点本身不变(仍只调 `compute_live_snapshot`,
  组装 equity/options 与调 `get_live_quotes` 都在 live.py 内),只把
  `snap.source` 写进响应。
- `schemas.py`:`LiveSnapshotOut` 加 `source: Literal["ibkr", "yahoo"]`。

**`app/core/config.py`(改)**

- `ibkr_gateway_url: str = "https://localhost:5000/v1/api"`
- `ibkr_gateway_timeout_seconds: float = 2.0`

**前端(改,极小)**

- `lib/api.ts`:`LiveSnapshot` 类型加 `source: "ibkr" | "yahoo"`。
- `LiveStatusBadge`:props 加 `source`,live 态文案 `Live · IBKR` /
  `Live · Yahoo (delayed)`;其余状态(Market closed / Manual / 行情不可用)不变。
- `LivePositionsTable` / `LivePnlTail`:把响应里的 `source` 透传给徽章。

**仓库/工具链**

- `.gitignore` 加 `gateway/`。
- `Makefile` 加 `gateway` target:`cd gateway/clientportal.gw && bin/run.sh root/conf.yaml`
  (目录不存在时打印下载指引退出)。
- README(中英)加 "IBKR Gateway 配置" 小节 + Phase 2 进度段更新。

## 错误处理

| 情形 | 行为 |
|---|---|
| Gateway 未启动 / 连接拒绝 / 超时 | `auth_ok()` → False,整体走 Yahoo,`source="yahoo"` |
| Gateway 已启动未登录 / 会话过期 | 同上(`authenticated: false`) |
| IBKR 在线但个别股票 symbol 解析不到 conid 或无价 | Yahoo 补洞;补完仍缺 → 503(strict) |
| IBKR 在线但期权解析不到 conid 或无 mark/last | 该期权按成本计,不报错 |
| snapshot 首次返回无价格字段 | 自动重试一次;重试后仍无 → 视为该 conid 无价 |
| IBKR 中途掉线(轮询 tick 之间) | 下一 tick 探测到 → 自动回落 Yahoo,徽章变 `Yahoo (delayed)` |
| Yahoo 也失败(双双不可用) | 503 `行情不可用`(现状语义) |

## 测试策略

全部离线单测,HTTP transport 注入 fake(与 Yahoo provider 同套路),不碰网络:

- `IBKRClientPortalClient`:auth 在线/离线/超时/异常 → `auth_ok` 布尔正确;
  预热只打一次;snapshot 空响应自动重试。
- `IBKRClientPortalProvider`:conid 缓存(同 symbol 第二次不再 search);
  价格前缀剥离(`C123.45` → `123.45`);缺价 symbol 缺席于结果。
- 期权解析:两步链路正确拼参(month 格式、strike、right);mark 优先 last 兜底。
- `ChainedMarketDataProvider`:在线全 IBKR / 在线部分缺 Yahoo 补洞 / 补洞仍缺
  503 / 离线全 Yahoo,四种路径 + `source` 值断言。
- `compute_live_snapshot`:有 option_marks → 期权实时市值进 positions 和曲线
  尾点;空 option_marks → 期权成本计(现状回归)。
- 前端:lint + build 照旧绿。

手动冒烟(真 Gateway,细节在实现计划):登录后徽章 `Live · IBKR` 且期权行出现
实时市值;关掉 Gateway 下一 tick 回落 `Live · Yahoo (delayed)` 且期权回成本;
双双杀掉 → `行情不可用`。

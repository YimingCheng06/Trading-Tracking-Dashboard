# M8 — 后端 HTTP API 层 设计

> 父路线图:`~/.claude/plans/dashboard-traking-ibkr-daily-activity-s-squishy-bee.md`。M8 是「前端页面」工作的前置:把已写好的服务层(导入、投影、P&L、快照、曲线)暴露成 HTTP 接口,供 M9 的前端页面消费。

## 目标

给 FastAPI app 加上业务接口,让前端能:上传 IBKR 日报、看账户列表、看持仓 / 成交 / 已实现盈亏 / 净值曲线、按需刷新行情。M8 不含前端 —— 那是 M9。

服务层已存在(M1–M6 + Phase 1.4),M8 只做「HTTP 包装 + 流水线编排」,不重写业务逻辑。

## 关键决定(已与用户确认)

- **上传纯本地、刷新才联网**(方案 B):`POST /statements/upload` 只做解析 + 重建 DB 投影,不联网;`POST /accounts/{id}/refresh-prices` 才调 Yahoo 拉行情、重建快照。
- 路径参数 `{account_id}` 用 **`broker_account_id`**(如 `U23072637`)—— 稳定、可读、与账本目录名一致。
- 跨账户「aggregate」汇总视图先不做。

## 接口

routers 放 `app/api/`,在 `main.py` 逐个 `include_router`(沿用 `health.py` 的模式)。响应一律 Pydantic 模型(`app/api/schemas.py`)。DB 会话用现成的 `get_db()` 依赖。

| 方法 + 路径 | 作用 | 联网 |
|---|---|---|
| `GET /accounts` | DB 里已导入的账户列表 | 否 |
| `POST /statements/upload` | 上传日报 CSV → 导入 + 重建投影 | 否 |
| `POST /accounts/{account_id}/refresh-prices` | 拉行情 → 重建快照 | **是** |
| `GET /accounts/{account_id}/positions` | 当前持仓 | 否 |
| `GET /accounts/{account_id}/trades` | 成交记录 | 否 |
| `GET /accounts/{account_id}/pnl` | 已实现盈亏汇总 | 否 |
| `GET /accounts/{account_id}/curve?mode=A\|B` | 净值曲线 | 否 |

### `GET /accounts`
查 `Account` 全表 → `[{broker_account_id, name, base_currency, broker}]`。无账户时返回 `[]`。

### `POST /statements/upload`
`multipart/form-data` 单文件。流水线(纯本地):
1. 把上传的 CSV 存到一个临时路径。
2. `import_statement(tmp_path, accounts_dir)` —— 解析、按账户拆分、去重写进账本 CSV。`accounts_dir = settings.data_dir / "accounts"`。
3. 对返回的每个 `account_id`:`AccountLedger(accounts_dir / account_id)` → `rebuild_account(session, ledger)` 重建该账户的 DB 投影。
4. 返回每账户的导入汇总(新增 trades / cash_flows / instruments / corporate_actions 条数)。

注:严格说上传不是 100% 离线 —— 非美元现金流(如 CAD 入金)在日报自带汇率没覆盖到那天时,`import_statement` 会做一次轻量的 ECB(Frankfurter)汇率查询并缓存。这跟方案 B 要避免的「上传时拉 Yahoo 行情建快照」是两码事(后者重、慢);FX 查询轻量且有缓存,不影响「上传快」的体验。

解析失败(非 CSV、列结构不对)→ `400`,带解析器抛出的 `ValueError` 信息。

### `POST /accounts/{account_id}/refresh-prices`
`rebuild_snapshots(session, account, provider)` —— `provider` 是一个 FastAPI 依赖,生产环境默认 `YahooFinanceProvider()`,测试用 `app.dependency_overrides` 注入假 provider 保持离线。返回写入的快照行数。账户不存在 → `404`。

### `GET /accounts/{account_id}/positions`
`compute_positions(session, account)` 给出每个持仓的数量 / 成本 / 均价;再对每个 instrument 查**最近一条** `PositionSnapshot`,合并出市值 / 未实现盈亏(无快照时这些字段为 `null`)。账户不存在 → `404`。

### `GET /accounts/{account_id}/trades`
查该账户全部 `Trade`,按 `executed_at` 倒序,join `Instrument` 拿 symbol。Phase 1 量级(几百行)直接全返回,不分页。

### `GET /accounts/{account_id}/pnl`
`compute_realized_pnl(session, account)` 的总额,加持仓数、币种等汇总字段。

### `GET /accounts/{account_id}/curve`
`compute_account_curve(session, account, mode)`,`mode` 查询参数 `A` / `B`,缺省 `B`。返回 `[{on_date, cumulative_pnl, pct}]`。非法 mode → `422`(用 `Literal["A","B"]` 让 FastAPI 自动校验)。

## 模块结构

- `app/api/schemas.py` — 所有响应的 Pydantic 模型(`AccountOut`、`PositionOut`、`TradeOut`、`PnlOut`、`CurvePointOut`、`UploadReportOut`、`RefreshResultOut`)。
- `app/api/accounts.py` — 账户相关 router(列表 + positions/trades/pnl/curve + refresh-prices)。
- `app/api/statements.py` — `POST /statements/upload` router。
- `app/api/deps.py` — 共用依赖:`get_account(account_id)`(按 `broker_account_id` 查 `Account`,找不到 raise `HTTPException(404)`)、`get_market_data_provider()`(默认 `YahooFinanceProvider`,可被 override)。
- `app/main.py` — 新增两个 `include_router`。

## 错误处理

- 账户不存在 → `404`,统一走 `get_account` 依赖。
- 上传文件解析失败 → `400`,信息取自 `ValueError`。
- `refresh-prices` 联网失败 → 让异常上抛(`500`);前端可重试,与方案 B 一致。
- 非法 `mode` → FastAPI 用 `Literal` 自动 `422`。

## 测试

pytest + FastAPI `TestClient`。每个测试用临时 SQLite(`get_db` 依赖 override 成测试会话,建表),真实跑 `import_statement` / `rebuild_account` / `compute_*`,只在 HTTP 边界断言。

- `upload`:用现成的合成 fixture `tests/fixtures/ibkr_flex_sample.csv`(M6 留下的,单账户 `U0000000`),POST 上去 → 断言返回的导入汇总、断言 `GET /accounts` 随后能看到该账户。
- `refresh-prices`:override `get_market_data_provider` 成假 provider(返回固定收盘价),离线验证。
- `positions` / `trades` / `pnl` / `curve`:先 upload(+ 必要时 refresh)铺数据,再 GET 断言。
- 账户不存在 → `404`;非法 `mode` → `422`。

## 范围

M8 = 支撑 M9 那 4 个页面(upload / positions / trades / pnl)所需的接口,加上 `GET /accounts` 驱动账户栏。不含前端、不含跨账户汇总、不含 IBKR 实时(Phase 2)。单一里程碑,一个实施计划。

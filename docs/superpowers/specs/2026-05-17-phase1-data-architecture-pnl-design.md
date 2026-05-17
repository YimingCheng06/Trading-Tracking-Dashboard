# Phase 1 数据架构 + P&L 引擎设计

- 日期:2026-05-17
- 范围:Phase 1 的数据流、CSV 账本、数据库 schema、货币/汇率层、P&L 引擎
- 不在本文范围:IBKR 日报解析器的具体列映射(需真实样本文件,另开 spec);实时 API(Phase 2);AI 工具层(Phase 3)

---

## 1. 背景与目标

个人交易追踪 dashboard。Phase 1 不依赖任何实时 API,靠手动导入 IBKR Daily Activity Statement 就能看到完整持仓、盈亏、交易历史。

本设计在原路线图基础上,根据用户确认的三点决策展开:

1. **文件即真相源** —— 一个用户可直接编辑的 CSV 账本是唯一真相源,数据库只是可重建的查询投影。用户能自己改程序识别错误的数据、补充未识别到的数据。
2. **自研 P&L 引擎**,提供两种盈亏比口径(IBKR/TWR 式 + 当前累计净入金式)。
3. **USD 为唯一规范货币** —— 账本里所有金额以 USD 记;非 USD 的 IBKR 数据在入库时折算;基础货币「选择」功能延后。

---

## 2. 架构与数据流

```
IBKR statement (CSV / XML)
      │  parser —— 只做去重 + 追加,绝不直接写 DB
      ▼
CSV 账本   data/accounts/<账户>/*.csv      ◄── 唯一真相源,用户可直接编辑
      │  projection builder —— 全量重建该账户的 DB 行
      ▼
SQLite     backend/data/app.db             ◄── 查询投影,可随时删掉重建
      │  read
      ▼
P&L 引擎  /  FastAPI  /  前端
```

核心规则:

- **解析器永不直接写数据库**。它只把去重后的新行追加进 CSV 账本。
- 账本一旦变化(导入完成,或用户改完文件触发「重新加载」)→ projection builder **全量重建该账户**的数据库行:删除该账户在各表的行 → 重读它的 CSV → 重新插入。全量重建,不做增量同步 —— 个人交易量小,简单、确定、不会产生漂移。
- **数据库是一次性的**。删掉 `app.db` 重启即可从账本重建。账本不丢,数据就不丢。

---

## 3. CSV 账本格式

### 3.1 目录结构

```
backend/data/
├── accounts/
│   └── <broker_account_id>/        # 每个账户一个目录,如 U1234567/
│       ├── account.toml            # 账户元数据:名称、基础货币、broker
│       ├── instruments.csv         # 证券主数据
│       ├── trades.csv              # 成交流水
│       ├── cash_flows.csv          # 出入金 / 股息 / 利息
│       └── corporate_actions.csv   # 拆股 / 分红 / 合并
├── fx_rates.csv                    # 全局汇率缓存(见第 6 节)
└── app.db                          # SQLite 投影,gitignored
```

`backend/data/` 已 gitignored。账本属于用户私有数据,不进版本库。

### 3.2 公共记账列

每个 CSV 的每一行前两列固定为记账列:

| 列 | 取值 | 含义 |
|---|---|---|
| `source` | `parsed` / `manual` | 程序导入 / 用户手改或新增 |
| `import_batch` | 批次 id 或 `manual` | 如 `2026-05-17T1430-dailyactivity`;手加行写 `manual` |

`source` 主要用于溯源展示;「重导入不覆盖手改」靠去重键保证(见 3.4),不依赖此列。

### 3.3 各文件字段

字段对应第 4 节的数据库列(去掉数据库自增主键、时间戳等)。金额一律 USD,同时保留原始货币列。

- **instruments.csv**:`symbol, asset_class, currency, exchange, name, conid, underlying_symbol, option_type, strike, expiry, multiplier`
- **trades.csv**:`trade_id, instrument, side, open_close, quantity, price, currency, fx_rate_to_usd, proceeds_orig, proceeds_usd, commission_orig, commission_usd, realized_pnl_ibkr, executed_at`
- **cash_flows.csv**:`flow_type, instrument, currency, fx_rate_to_usd, amount_orig, amount_usd, description, external_id, occurred_at`
- **corporate_actions.csv**:`instrument, action_type, ex_date, ratio, description, external_id`

`instrument` 列以一个稳定的文本键引用 instruments.csv 里的某证券(如股票用 `AAPL`,期权用 OCC 风格符号),projection builder 解析时映射到 DB 外键。

### 3.4 去重键

解析器追加前先按去重键查重,键已存在则跳过:

| 文件 | 去重键 |
|---|---|
| trades | `账户 + trade_id` |
| cash_flows | `账户 + external_id`(缺失则 `flow_type + occurred_at + amount` 的 hash) |
| instruments | `symbol + asset_class + 期权字段(strike/expiry/option_type)` |
| corporate_actions | `instrument + action_type + ex_date` |

**重导入不覆盖手改**:用户改过的某条 `parsed` 行,重导入同一份日报时,解析器发现其去重键已存在 → 跳过,改动天然保住。
**已知边界**:若用户改的恰好是去重键本身的字段,重导入可能再插回原始行 —— spec 记录此边界,实现时在「重新加载」校验里给出警告。

---

## 4. 数据库 Schema

SQLAlchemy 2.0 typed `Mapped` 风格,定义在 `backend/app/db/models.py`。SQLite 本地,Postgres 云端,一份 schema 通用。

### 4.1 六张表

| 表 | 用途 |
|---|---|
| `accounts` | 账户(多账户、未来多用户) |
| `instruments` | 证券主数据,含期权预留字段 |
| `trades` | 成交流水 |
| `cash_flows` | 出入金 / 股息 / 利息 |
| `positions_snapshot` | 每日持仓快照(P&L 时间序列用) |
| `corporate_actions` | 拆股 / 分红 / 合并 |

### 4.2 货币列约定

- 账本与数据库金额一律 USD;每条带金额的记录保留 `原始货币 + 原始金额 + fx_rate_to_usd + USD 金额`。
- USD 金额列命名 `*_usd`(`proceeds_usd`、`commission_usd`、`amount_usd`、`market_value_usd`、`unrealized_pnl_usd`),`fx_rate_to_usd` 为所用汇率。
- 折算在解析/入库时完成,故 `*_usd` 与 `fx_rate_to_usd` 为 **NOT NULL**(USD 交易 fx_rate = 1)。

### 4.3 溯源列

四张投影表(`trades`、`cash_flows`、`instruments`、`corporate_actions`)各加两列:

- `source` —— 枚举 `RecordSource.PARSED / MANUAL`
- `import_batch` —— 字符串,可空

不单独建 import_batches 表 —— 导入历史按 `import_batch` 分组即可查出(YAGNI;以后要存文件名/错误详情再加)。

### 4.4 去重约束

数据库唯一约束作为投影干净性的兜底(实际去重发生在 CSV 追加阶段):

- `accounts.broker_account_id` 唯一
- `trades(account_id, trade_id)` 唯一
- `positions_snapshot(account_id, instrument_id, snapshot_date)` 唯一

### 4.5 相对 Phase 1.1 已建 schema 的改动

当前 worktree 分支 `worktree-phase1-db-schema` 上已有一版 schema。本设计需要的调整:

1. 已删除 `Trade.tax` 列与 `CashFlowType.TAX`(税作为独立功能延后)。
2. `*_base` 列改名 `*_usd`;`fx_rate_to_base` → `fx_rate_to_usd`。
3. `*_usd` 与 `fx_rate_to_usd` 由可空改为 NOT NULL。
4. `Trade.realized_pnl` 改名 `realized_pnl_ibkr`,明确它是 IBKR 报的值(与自研引擎算出的区分);保持可空。
5. `trades / cash_flows / instruments / corporate_actions` 各加 `source`、`import_batch` 两列。
6. 调整后重新生成单个 Alembic migration。

---

## 5. P&L 引擎

`backend/app/services/pnl/engine.py` 里的一个服务,**只读数据库投影**(`trades` / `cash_flows` / `positions_snapshot`),全部以 USD 计算。

### 5.1 成本法与盈亏

- **FIFO 默认**;成本法做成可插拔接口,均价法以后作为选项。
- **已实现盈亏(自研)**:卖出时 FIFO 匹配买入批次,算出每笔平仓的已实现盈亏。`trades.realized_pnl_ibkr`(IBKR 报的值)并存,前端并排显示做交叉核对 —— 即「同时计算」。
- **未实现盈亏**:持仓 `(现价 − 平均成本) × 数量 × 乘数`,现价取自 `positions_snapshot`。

### 5.2 净值曲线 + 两种盈亏比口径

引擎产出一条每日时间序列。对每一天 `d`:

- `组合价值(d)` = 当日持仓市值 + 现金余额
- `累计净入金(d)` = Σ(入金 − 出金),截至 d
- `累计盈亏(d)` = 组合价值(d) − 累计净入金(d)

**Mode A —— IBKR / 时间加权(TWR)**

- 每日收益率 `r(d) = (组合价值(d) − 当日净外部流入(d)) / 组合价值(d−1) − 1`
- 累计 `TWR(d) = Π(1 + r(i)), i ≤ d` 再减 1
- 外部现金流按当日边界处理。过去的点冻结,后续入金不改变更早的 `r(i)`。

**Mode B —— 当前累计净入金**

- 对序列中每一天 `d`:`%(d) = 累计盈亏(d) ÷ 当前累计净入金`
- 「当前累计净入金」= 序列最新一天的累计净入金。新入金改变此分母 → 整条曲线重算。
- 验算(确认例子):第 5 天累计盈亏 −100、第 10 天后累计净入金 10,000 → 第 5 天点 = −100 / 10,000 = −1%;第 10 天 = −199 / 10,000 ≈ −2%。
- 边界:当前累计净入金 ≤ 0 时不能作分母 → 退化为显示绝对盈亏额并在 UI 标注。

### 5.3 引擎接口

- `compute_positions(account)` → 当前持仓(数量、均价、市值、未实现盈亏)
- `compute_realized_pnl(account, period, groupby)` → 已实现盈亏汇总(按时间段 / 标的 / 资产类别)
- `compute_equity_curve(account, mode)` → 每日序列 `(日期, 组合价值, 累计盈亏, 百分比)`,`mode ∈ {A, B}`,前端可切换

### 5.4 依赖

净值曲线需要每日 `positions_snapshot`(带收盘价),由 YahooFinanceProvider + 每日快照任务喂数据(路线图 Phase 1.4)。在此之前,引擎仍能从 `trades` 单独算出持仓与已实现盈亏 —— 仅曲线需等快照。

---

## 6. 货币与汇率

### 6.1 规范货币

USD 为 Phase 1 唯一规范货币。账本里所有金额以 USD 记;IBKR 文件若为其他货币,**在解析/入库那一刻折算成 USD** 再写进账本。

### 6.2 `FxRateProvider` 接口

沿用 adapter 模式(同 `MarketDataProvider` / `NewsProvider`)。Phase 1 两个实现,按优先级:

1. **`StatementFxProvider`(首选)** —— 直接用 IBKR 日报里自带的汇率,是 IBKR 实际应用于这些交易的那条,最准、零外部依赖。
2. **`EcbFxProvider`(兜底)** —— 欧洲央行每日参考汇率,免费、无需 API key、含历史数据,通过 Frankfurter API(`api.frankfurter.app`,封装 ECB)按日期查询。日频,无需实时。

取到的汇率缓存进全局 `data/fx_rates.csv`(列:`date, base, quote, rate`),避免重复请求。**但某行交易实际所用汇率以该行记录的 `fx_rate_to_usd` 为准**;缓存只是查询加速,非真相源。

### 6.3 未来「基础货币选择」(不在 Phase 1)

将来若开放用户自选基础货币用于显示:UI **必须提示** —— 显示金额可能因汇率时点差异而与实际有偏差。本条仅作记录,Phase 1 不实现。

---

## 7. 测试策略

TDD(测试先行)。

- **模型层**:in-memory SQLite,各表 round-trip、关系、唯一约束。(Phase 1.1 已有 13 个测试。)
- **CSV 账本层**:小型 fixture 账本,验证读 / 去重追加 / 字段往返。
- **projection builder**:给定 fixture 账本 → 重建 → 断言 DB 行;重复重建结果幂等。
- **FX 层**:`StatementFxProvider` 用样本数据;`EcbFxProvider` mock HTTP 响应。
- **P&L 引擎**:第 5.2 节的验算例子直接做成 Mode A / Mode B 各一个测试用例,预期盈亏手工核对;FIFO 已实现盈亏用手算样例。

---

## 8. 实施顺序

本设计落地拆为若干里程碑(IBKR 解析器本身另开 spec,需真实样本):

| 里程碑 | 内容 | 依赖 |
|---|---|---|
| M1 | Schema 调整(溯源列、`*_usd` 改名 + NOT NULL)+ 重新生成 migration | — |
| M2 | CSV 账本子系统(读 / 去重追加 / 账户目录) | — |
| M3 | projection builder(CSV → DB 全量重建) | M1, M2 |
| M4 | FX 层(`FxRateProvider` + ECB + statement 实现) | — |
| M5 | P&L 引擎(FIFO、已实现/未实现、两种口径曲线) | M3 |
| M6 | IBKR 日报解析器(另开 spec,需真实样本 CSV) | M2, M4 |

---

## 9. 已锁定决策的关系

- 锁定决策 #2(P&L 按用户选择的基础货币)→ 本设计细化为:Phase 1 用 USD 作唯一规范货币,基础货币「选择」延后。
- 税:不在 Phase 1 计算,作为独立功能延后。
- 资产范围、adapter 模式、UI 风格等其余锁定决策不变。

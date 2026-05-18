# Phase 1 M6 — IBKR Flex Query CSV 解析器 设计

> 父 spec:`2026-05-17-phase1-data-architecture-pnl-design.md`(M6 在 phasing 表中标注「另开 spec,需真实样本」)。本文档是那份 spec。

## 目标

把一份 IBKR **Flex Query 导出的 CSV** 解析成 M2 的 `Ledger*` 行模型,去重追加进账户的 CSV 账本。解析器只读文件、产出行、追加;绝不直接写 DB(DB 由 M3 projection builder 重建)。

## 输入文件的真实结构

真实样本(账户 `U23072637`)是 **Flex Query 导出**,不是标准 Activity Statement。一个文件里**纵向堆叠 3 个 section**,每个 section 以自己的表头行开头(第 1 列恒为 `ClientAccountID`):

### Section 1 — Trades(28 列)

```
ClientAccountID,CurrencyPrimary,AssetClass,Symbol,Strike,Expiry,DateTime,
Put/Call,TradeDate,Quantity,TradePrice,TradeMoney,Taxes,NetCash,ClosePrice,
CostBasis,FifoPnlRealized,OrigTradePrice,OrigTradeDate,Buy/Sell,OrderTime,
OpenDateTime,ChangeInPrice,ChangeInQuantity,OrderType,IBCommission,
IBCommissionCurrency,Conid
```

> 去重需要,Flex Query 还应勾选 `IBExecID` 列(见下「trade_id」)。解析器对其有无都能跑。

- `AssetClass`:`STK` → `AssetClass.STOCK`;`OPT` → `AssetClass.OPTION`;`CASH` → 外汇(见下)。
- `Symbol`:股票是 `AAOI`;期权是 IBKR OCC 串 `AAOI  260417P00135000`(直接整串当 instrument 标识)。
- `DateTime`:`2026-03-26;15:30:58 EDT` —— 分号分隔日期与时间,带时区缩写 `EDT`/`EST`(= US/Eastern)。
- 期权 Strike / Expiry / Put-Call 三列都有值,不必解析 OCC 串。

### Section 2 — Corporate Actions(12 列)

```
ClientAccountID,CurrencyPrimary,Symbol,Strike,Expiry,Put/Call,Date/Time,
Amount,Quantity,CostBasis,FifoPnlRealized,Conid
```

样本里 2 行 = 1 个事件:同一时间戳下 `PELI.OLD −200` / `GLND +200`。

### Section 3 — Cash Transactions(14 列)

```
ClientAccountID,AssetClass,Symbol,Conid,Strike,Expiry,Put/Call,Date/Time,
SettleDate,AvailableForTradingDate,Amount,CurrencyPrimary,Type,DividendType
```

`Type` 列直接给出类别。`Date/Time` 可能是完整时间戳,也可能只有日期 `2025-11-21`。

## 映射规则

### Trades → `LedgerInstrument` + `LedgerTrade`

每笔非外汇成交产出一条 `LedgerInstrument` 和一条 `LedgerTrade`。M5 引擎的约定:`quantity` 存正数、`commission` 存正数幅值、`proceeds` 存 gross(price×qty,期权 ×100 已含在 `TradeMoney` 里)。

| Ledger 字段 | 来源 |
|---|---|
| `LedgerInstrument.symbol` | `Symbol`(原样,期权用完整 OCC 串) |
| `LedgerInstrument.asset_class` | `STK`→STOCK / `OPT`→OPTION |
| `LedgerInstrument.currency` | `CurrencyPrimary` |
| `LedgerInstrument.conid` | `Conid` |
| 期权:`underlying_symbol` | `Symbol` 中第一个空格前的部分 |
| 期权:`option_type` / `strike` / `expiry` | `Put/Call` / `Strike` / `Expiry` |
| 期权:`multiplier` | `100` |
| `LedgerTrade.trade_id` | 见下「trade_id」 |
| `LedgerTrade.instrument` | = `LedgerInstrument.symbol` |
| `LedgerTrade.side` | `Buy/Sell` 列 |
| `LedgerTrade.quantity` | `abs(Quantity)` |
| `LedgerTrade.price` | `TradePrice` |
| `LedgerTrade.proceeds_orig` / `proceeds_usd` | `abs(TradeMoney)` |
| `LedgerTrade.commission_orig` / `commission_usd` | `abs(IBCommission)` |
| `LedgerTrade.fx_rate_to_usd` | `1`(成交全是 USD) |
| `LedgerTrade.realized_pnl_ibkr` | `FifoPnlRealized` |
| `LedgerTrade.executed_at` | `DateTime` 解析 |
| `LedgerTrade.open_close` | `None`(本导出无 Code 列;FIFO 引擎自行判断开平仓) |

**`trade_id`** —— 跨日报去重的键,必须可靠:用户逐份导入日报,相邻日报日期范围重叠,同一笔成交会在多份里出现;`trade_id` 相同则 `LedgerTable` 跳过、不重复计入。

- **首选 `IBExecID`**:IBKR 每笔成交执行的全局唯一 ID。同一笔成交在任何日报里 ID 不变 → 跨日报去重 100% 可靠。Flex Query 需勾选 `IBExecID` 列。
- **兜底:内容哈希**:`IBExecID` 列缺失时,退回 `conid|datetime|quantity|price|trademoney|commission` 的 SHA-1 前 16 位。注意此键**不防撞** —— IBKR 把一个订单拆成多笔时,同秒同价同量的拆单会被误判为同一笔而漏计。仅作没有 `IBExecID` 时的降级方案。

解析器逻辑:`trade_id = row.get("IBExecID") or _content_hash(...)`。

### 外汇 CASH 行 → 语句内 FX 汇率

`AssetClass=CASH` 的行是 `USD.CAD` 货币兑换(余额中性)。**不产出 trade,也不产出 cash flow**。它们的作用是提供 IBKR 自用汇率:

- `TradePrice` 是 USD.CAD,即「1 USD = TradePrice CAD」。
- CAD→USD 的换算率 = `1 / TradePrice`。
- 收集成 `dict[(currency, date), Decimal]` 喂给 `build_fx_provider(statement_rates)`。

### Cash Transactions → `LedgerCashFlow`

| 文件 `Type` | `CashFlowType` |
|---|---|
| `Deposits/Withdrawals` | `Amount > 0` → `DEPOSIT`;`< 0` → `WITHDRAWAL` |
| `Other Fees` | `FEE` |
| `Broker Interest Received` | `INTEREST` |
| `Dividends` | `DIVIDEND` |
| `Withholding Tax` | `OTHER`(`CashFlowType.TAX` 已按用户要求移除;映 `OTHER`、`description` 保留 `"Withholding Tax"`,现金能对上,未来「地区报税」功能再认领) |

- `currency` ← `CurrencyPrimary`;`amount_orig` ← `Amount`;`occurred_at` ← `Date/Time`(兼容纯日期)。
- `amount_usd` / `fx_rate_to_usd`:USD 行 fx=1;非 USD(入金多为 CAD)走 FX provider,`convert_to_usd` 算 `amount_usd`,`fx_rate_to_usd` = provider 给出的 rate。
- `instrument` ← `Symbol`(分红/预扣税有,其余为空)。
- `external_id`:合成内容哈希(`type|datetime|amount|symbol`)。
- `description`:`Type`(预扣税额外保留 `"Withholding Tax"`)。

### Corporate Actions → `LedgerCorporateAction`

同一时间戳的多行配成一个事件。`.OLD` 后缀是 IBKR 给退市/改名旧代码的标记 → `CorporateActionType.SYMBOL_CHANGE`。产出一条 `LedgerCorporateAction`:`instrument` = 新代码、`ratio` = 新数量/旧数量、`description` = `"PELI.OLD → GLND (1:1)"`、`ex_date` = 时间戳日期、`external_id` = 合成哈希。成本基础跨改名的结转是 P&L 引擎的后续工作,不在 M6。

## 模块与接口

`backend/app/services/parsers/ibkr_flex.py`

```python
@dataclass(frozen=True)
class ParsedStatement:
    account_id: str
    instruments: list[LedgerInstrument]
    trades: list[LedgerTrade]
    cash_flows: list[LedgerCashFlow]
    corporate_actions: list[LedgerCorporateAction]

def parse_flex_csv(
    path: Path, *, fx_provider: FxRateProvider | None = None
) -> ParsedStatement: ...

def import_statement(path: Path, ledger: AccountLedger) -> ImportReport: ...
```

- `parse_flex_csv`:纯解析。先抽外汇行得到 `statement_rates`;`fx_provider` 缺省时 `build_fx_provider(statement_rates)`,测试可注入离线 provider。
- `import_statement`:`parse_flex_csv` → 把四类行 `append` 进 `AccountLedger` 的四张表;靠 `LedgerTable` 的 `dedup_key` 去重 —— 重导同一份文件是 no-op,用户手改的行不被覆盖。返回每张表的 `added/skipped` 汇总。

## 错误处理

- 未知 section 表头、未知 `AssetClass`、未知 `Type` → 抛 `ValueError`,附行内容,**不静默跳过**。
- 解析失败的单行同理上抛 —— 坏数据要暴露(与 `LedgerTable.read()` 的既有约定一致)。

## 测试

TDD。**不提交真实 `Tracking.csv`(真实账户号 + 全部交易)**。测试用一份手写的脱敏合成 fixture `backend/tests/fixtures/ibkr_flex_sample.csv`,覆盖:STK 买/卖、OPT 买/卖、外汇 CASH 行、每种 Cash `Type`、一对 Corporate Action 行。FX 用注入的 `StatementFxProvider`/`ChainedFxProvider` 保持离线。`import_statement` 的幂等性(重导一次 `added=0`)单独测。

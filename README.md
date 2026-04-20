# Trading Tracking Dashboard

个人交易追踪 dashboard —— 导入 IBKR Daily Activity Statement，展示持仓与盈亏，后续接入实时 API + BYOK AI 分析。

## 架构

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic (uv 包管理)
- **Frontend**: Next.js 16 (App Router) + TypeScript + Tailwind v4 (React 19.2)
- **DB**: SQLite (本地) → PostgreSQL (云端)

详细路线图：`~/.claude/plans/dashboard-traking-ibkr-daily-activity-s-squishy-bee.md`

## 快速开始

前置：`node >= 20.9`，`python >= 3.12`，`uv`（`curl -LsSf https://astral.sh/uv/install.sh | sh`）。

```bash
make install          # 装依赖
make dev              # 同时启动 backend (:8000) + frontend (:3000)
```

访问 [http://localhost:3000](http://localhost:3000) 会重定向到 `/dashboard`。

### 单独启动

```bash
make dev-backend      # 仅后端 (http://localhost:8000/docs 看 OpenAPI)
make dev-frontend     # 仅前端
```

## 目录结构

```
backend/
  app/
    api/              # FastAPI 路由
    core/             # 配置
    db/               # SQLAlchemy models + migrations
    services/
      providers/      # 行情/持仓 adapter (IBKR / Yahoo)
      parsers/        # Statement 解析
      pnl/            # 盈亏计算
      news/           # 新闻 adapter (BYOK)
    mcp_server/       # AI 工具层 (MCP + OpenAI function spec)
  alembic/
frontend/
  app/                # Next.js App Router 页面
  lib/                # 前端工具库 (api client, ai providers)
```

## 测试与 Lint

```bash
make test             # pytest
make lint             # ruff + eslint
```

## 进度 (Progress)

### ✅ Phase 0 — 脚手架 (2026-04-19)
- Backend：FastAPI + SQLAlchemy 2.0 + Alembic，uv 管理依赖，`/health` 端点在线
- Frontend：Next.js 16 (App Router) + React 19.2 + Tailwind v4，TradingView 深色 + Robinhood 极简 token
- 根 `Makefile`：`make dev` 同启 backend (:8000) + frontend (:3000)
- 端到端验证：dashboard 能调 `/health` 并显示 JSON

### ✅ Phase 0.5 — Discord 风格工作区外壳 (2026-04-19)
- 所有路由迁入 `app/(workspace)/` route group
- 双栏导航：
  - **AccountRail** (72px)：账户即「server」，圆→圆角方 morph，active 光晕 + 白色 indicator bar
  - **ModuleRail** (64px)：**纯图标菜单，hover 才出 tooltip**（按用户偏好），左侧 3px accent bar 标记 active
- 菜单分组：Portfolio / Activity / Analysis / Intelligence / Settings（共 14 个子页面）
- Dashboard 页重做：hero 渐变卡 + 超大数字 + 4 段阶段进度条 + 指标卡 hover radial glow + 呼吸状态点
- 除 dashboard 外所有页面为 `PlaceholderPage` 占位（带 Phase 1 待办说明）
- `next build` 全绿，16 条路由全部生成

### ⏳ Phase 1 — 导入 + 核心数据（待开始）
- [ ] IBKR Daily Activity Statement 解析器（CSV / HTML）
- [ ] Trade / Position / Cashflow DB schema + Alembic migration
- [ ] FIFO / 均价成本基础引擎 + 基础货币 FX 转换
- [ ] `/upload` 页接入上传 → 解析 → 持久化链路
- [ ] `/positions`、`/trades`、`/holdings` 真实数据接入
- [ ] `/pnl` 页实现已实现 / 未实现 P&L 分解

### 🔜 Phase 2 — 实时数据（规划）
- IBKR Client Portal / Realtime adapter（按锁定的 fallback 链）
- Yahoo Finance 兜底 quotes
- `/orders` 实时订单状态

### 🔜 Phase 3 — 情报层（规划）
- BYOK AI 工具层（MCP Server + OpenAI function spec）
- 标准工具：`get_portfolio_snapshot` / `get_pnl` / `get_trade_history` / `get_position_detail` / `get_news_for_holdings` / `get_market_context`
- BYOK News Provider（Marketaux / Finnhub / Alpha Vantage）

### 🔜 Phase 4 — 部署（规划）
- PostgreSQL 迁移
- Docker 容器化
- 云端发布


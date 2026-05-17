# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository

GitHub: https://github.com/YimingCheng06/Trading-Tracking-Dashboard

## What this is

Personal trading-tracking dashboard. Imports IBKR Daily Activity Statements, computes positions & P&L, and (later) layers on realtime quotes and a BYOK AI/news analysis layer. The project is built in numbered phases — see README.md "进度 (Progress)" for current status and the authoritative roadmap at `~/.claude/plans/dashboard-traking-ibkr-daily-activity-s-squishy-bee.md` (read it before starting feature work).

## Commands

The root `Makefile` is the entrypoint — prefer it over invoking tools directly.

```bash
make install          # uv sync (backend) + npm install (frontend)
make dev              # backend :8000 + frontend :3000 together (Ctrl+C stops both)
make dev-backend      # backend only — OpenAPI at http://localhost:8000/docs
make dev-frontend     # frontend only
make test             # pytest (backend)
make lint             # ruff check (backend) + eslint (frontend)
```

Backend Python commands run through uv with `--no-sync` (deps assumed installed); `uv` is expected at `$HOME/.local/bin/uv`. To run a single test:

```bash
cd backend && uv run --no-sync pytest tests/test_file.py::test_name
cd backend && uv run --no-sync pytest -k "keyword"
```

Alembic (run from `backend/`): `uv run --no-sync alembic revision --autogenerate -m "msg"` then `alembic upgrade head`.

## Architecture

Two-part monorepo with **no shared code** — `backend/` and `frontend/` communicate only over HTTP.

### Backend (`backend/`) — Python 3.12, FastAPI, SQLAlchemy 2.0, uv

`app/main.py` builds the FastAPI app, adds CORS (origins from `settings.cors_origins`), and includes routers from `app/api/`. Routes are wired one router at a time in `main.py`.

- `app/core/config.py` — `Settings` (pydantic-settings, reads `backend/.env`). `settings` is a module-level singleton; import it, don't re-instantiate. `data_dir` auto-creates `backend/data/` (gitignored, holds the SQLite DB).
- `app/db/base.py` — `Base` (SQLAlchemy 2.0 `DeclarativeBase`), `engine`, `SessionLocal`, and `get_db()` FastAPI dependency. The `check_same_thread` connect-arg is applied only for SQLite, so swapping `database_url` to Postgres needs no code change.
- `app/services/` — domain logic split by concern, mostly scaffolding pending Phase 1:
  - `providers/` — market-data/position adapters (IBKR, Yahoo) behind a common interface
  - `parsers/` — IBKR statement parsing (CSV/HTML)
  - `pnl/` — FIFO / average-cost engine + base-currency FX conversion
  - `news/` — BYOK news adapters (Marketaux / Finnhub / Alpha Vantage)
- `app/mcp_server/` — AI tool layer (MCP server + OpenAI function spec), Phase 3.
- `alembic/env.py` — imports `Base.metadata` for autogenerate and pulls the URL from `settings`, so new models are picked up automatically once their module is imported. Migrations are autogenerate-driven.

### Frontend (`frontend/`) — Next.js 16 App Router, React 19.2, TypeScript, Tailwind v4

**Important:** `frontend/AGENTS.md` (referenced by `frontend/CLAUDE.md`) warns this is Next.js 16 with breaking changes vs. older training data — consult `node_modules/next/dist/docs/` before writing Next.js code.

- All app routes live under `app/(workspace)/` (a route group) and share `(workspace)/layout.tsx`, a Discord-style three-rail shell: `AccountRail` (accounts-as-servers) + `ModuleRail` (icon-only nav, tooltip on hover) + `Sidebar`. `app/page.tsx` redirects `/` → `/dashboard`.
- `app/(workspace)/_config/workspace.ts` is the **single source of truth** for navigation — `accounts` and `moduleGroups` drive both rails. Add a page by adding a route folder *and* a `ModuleItem` here.
- `lib/api.ts` — backend client. `apiGet<T>` wraps `fetch` against `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`); add typed endpoints to the exported `api` object.
- Most pages currently render `PlaceholderPage`; `dashboard/page.tsx` is the only fully built page. Design language: TradingView dark + Robinhood minimal tokens (see `app/globals.css`).

## Conventions

- Backend lint via ruff (line-length 100, rules `E,F,I,N,UP,B,SIM`); pytest runs in `asyncio_mode = "auto"` so async tests need no decorator.
- Commits in this repo: do **not** add a `Co-Authored-By: Claude` trailer.

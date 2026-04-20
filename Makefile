.PHONY: help install install-backend install-frontend dev dev-backend dev-frontend test lint clean

UV := $(HOME)/.local/bin/uv

help:
	@echo "Trading Tracking Dashboard"
	@echo ""
	@echo "  make install         install backend + frontend deps"
	@echo "  make dev             run backend (:8000) + frontend (:3000)"
	@echo "  make dev-backend     backend only"
	@echo "  make dev-frontend    frontend only"
	@echo "  make test            run backend tests"
	@echo "  make lint            run ruff + eslint"
	@echo "  make clean           remove build artifacts"

install: install-backend install-frontend

install-backend:
	cd backend && $(UV) sync

install-frontend:
	cd frontend && npm install

dev:
	@echo "Starting backend (:8000) and frontend (:3000). Ctrl+C to stop both."
	@(trap 'kill 0' EXIT; \
	  cd backend && $(UV) run --no-sync uvicorn app.main:app --reload --port 8000 & \
	  cd frontend && npm run dev & \
	  wait)

dev-backend:
	cd backend && $(UV) run --no-sync uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && $(UV) run --no-sync pytest

lint:
	cd backend && $(UV) run --no-sync ruff check .
	cd frontend && npx eslint .

clean:
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/__pycache__
	rm -rf frontend/.next frontend/out
	find . -type d -name "__pycache__" -exec rm -rf {} +

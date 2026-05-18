"""Shared FastAPI dependencies for the API layer."""

from pathlib import Path

from app.core.config import settings


def get_accounts_dir() -> Path:
    """The directory holding per-account CSV ledgers — overridable in tests."""
    accounts_dir = settings.data_dir / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)
    return accounts_dir

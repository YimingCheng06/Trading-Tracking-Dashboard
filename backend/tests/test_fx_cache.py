from datetime import date
from decimal import Decimal

from app.services.fx.cache import FxRateCache


def test_get_returns_none_for_missing_file(tmp_path):
    cache = FxRateCache(tmp_path / "fx_rates.csv")
    assert cache.get("EUR", date(2026, 1, 15)) is None


def test_put_then_get_round_trips(tmp_path):
    cache = FxRateCache(tmp_path / "fx_rates.csv")
    cache.put("EUR", date(2026, 1, 15), Decimal("1.08"))

    assert cache.get("EUR", date(2026, 1, 15)) == Decimal("1.08")


def test_get_misses_on_different_currency_or_date(tmp_path):
    cache = FxRateCache(tmp_path / "fx_rates.csv")
    cache.put("EUR", date(2026, 1, 15), Decimal("1.08"))

    assert cache.get("GBP", date(2026, 1, 15)) is None
    assert cache.get("EUR", date(2026, 1, 16)) is None


def test_csv_header_columns(tmp_path):
    path = tmp_path / "fx_rates.csv"
    FxRateCache(path).put("EUR", date(2026, 1, 15), Decimal("1.08"))
    header = path.read_text().splitlines()[0]
    assert header == "date,base,quote,rate"


def test_duplicate_put_keeps_first_value(tmp_path):
    """put appends; get returns the first cached value for a key."""
    cache = FxRateCache(tmp_path / "fx_rates.csv")
    cache.put("EUR", date(2026, 1, 15), Decimal("1.08"))
    cache.put("EUR", date(2026, 1, 15), Decimal("9.99"))

    assert cache.get("EUR", date(2026, 1, 15)) == Decimal("1.08")

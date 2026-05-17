"""Factory for the default FX rate provider.

Assembles the priority chain mandated by the spec — IBKR statement rates
first, then ECB daily rates (cached in `data/fx_rates.csv`).
"""

from datetime import date
from decimal import Decimal

from app.core.config import settings
from app.services.fx.cache import FxRateCache
from app.services.fx.ecb import EcbFxProvider
from app.services.fx.provider import ChainedFxProvider, StatementFxProvider


def build_fx_provider(
    statement_rates: dict[tuple[str, date], Decimal] | None = None,
) -> ChainedFxProvider:
    """Build the default FX provider: statement rates first, then ECB.

    `statement_rates` are the FX rates the IBKR statement itself reports
    (the parser supplies these). ECB rates are fetched on demand via the
    Frankfurter API and cached in `data/fx_rates.csv`.
    """
    statement = StatementFxProvider(statement_rates or {})
    ecb = EcbFxProvider(FxRateCache(settings.data_dir / "fx_rates.csv"))
    return ChainedFxProvider([statement, ecb])

"""The 7 domain enums must be importable from app.db.enums without importing the ORM."""

from app.db import enums


def test_all_domain_enums_exposed():
    assert enums.AssetClass.STOCK.value == "STOCK"
    assert enums.OptionType.CALL.value == "CALL"
    assert enums.TradeSide.BUY.value == "BUY"
    assert enums.OpenClose.OPEN.value == "OPEN"
    assert enums.CashFlowType.DIVIDEND.value == "DIVIDEND"
    assert enums.CorporateActionType.SPLIT.value == "SPLIT"
    assert enums.RecordSource.PARSED.value == "PARSED"


def test_models_reexports_same_enum_objects():
    """models.py must re-export the identical enum objects, not redefine them."""
    from app.db import models

    assert models.AssetClass is enums.AssetClass
    assert models.RecordSource is enums.RecordSource

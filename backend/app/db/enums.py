"""Domain enums shared by the ORM models and the CSV ledger layer."""

import enum


class AssetClass(enum.Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    OPTION = "OPTION"


class OptionType(enum.Enum):
    CALL = "CALL"
    PUT = "PUT"


class TradeSide(enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OpenClose(enum.Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"


class CashFlowType(enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    OTHER = "OTHER"


class CorporateActionType(enum.Enum):
    SPLIT = "SPLIT"
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    MERGER = "MERGER"
    SPINOFF = "SPINOFF"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"


class RecordSource(enum.Enum):
    PARSED = "PARSED"
    MANUAL = "MANUAL"

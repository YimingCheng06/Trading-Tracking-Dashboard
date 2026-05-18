"""Pydantic response models for the HTTP API."""

from pydantic import BaseModel


class AccountOut(BaseModel):
    broker_account_id: str
    name: str
    base_currency: str
    broker: str


class AppendCountOut(BaseModel):
    added: int
    skipped: int


class AccountImportOut(BaseModel):
    broker_account_id: str
    instruments: AppendCountOut
    trades: AppendCountOut
    cash_flows: AppendCountOut
    corporate_actions: AppendCountOut


class UploadReportOut(BaseModel):
    accounts: list[AccountImportOut]

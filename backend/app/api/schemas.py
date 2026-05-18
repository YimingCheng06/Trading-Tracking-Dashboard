"""Pydantic response models for the HTTP API."""

from pydantic import BaseModel


class AccountOut(BaseModel):
    broker_account_id: str
    name: str
    base_currency: str
    broker: str

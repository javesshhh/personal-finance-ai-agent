from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.transaction import TransactionCategory


class TransactionCreate(BaseModel):
    date: date
    description: str
    amount: Decimal
    category: TransactionCategory = TransactionCategory.OTHER
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_nonzero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("Transaction amount cannot be zero")
        return v


class TransactionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    date: date
    description: str
    amount: Decimal
    category: TransactionCategory
    notes: str | None


class SpendingByCategory(BaseModel):
    category: TransactionCategory
    total: Decimal
    count: int


class MonthComparison(BaseModel):
    category: TransactionCategory
    month_a_total: Decimal
    month_b_total: Decimal
    delta: Decimal
    delta_pct: float

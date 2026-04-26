from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SubscriptionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    latest_amount: Decimal
    previous_amount: Decimal | None
    last_charged: date
    frequency_days: int
    waste_score: int | None
    waste_reason: str | None
    is_active: bool


class PriceChangeAlert(BaseModel):
    name: str
    previous_amount: Decimal
    latest_amount: Decimal
    change_pct: float

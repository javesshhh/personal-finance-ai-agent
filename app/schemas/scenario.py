from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.transaction import TransactionCategory


class SpendingChange(BaseModel):
    category: TransactionCategory
    reduction_pct: float  # 0-100; positive = reduction

    @field_validator("reduction_pct")
    @classmethod
    def pct_must_be_valid(cls, v: float) -> float:
        if not (0 < v <= 100):
            raise ValueError("reduction_pct must be between 0 and 100")
        return v


class ScenarioRequest(BaseModel):
    session_id: str | None = None  # resolved by API layer; None = use default
    spending_changes: list[SpendingChange]
    target_amount: Decimal
    target_description: str  # e.g., "MacBook Pro"
    extra_monthly_savings: Decimal = Decimal("0")


class ScenarioResult(BaseModel):
    months_to_goal: int | None
    projected_monthly_savings: Decimal
    current_monthly_savings: Decimal
    narrative: str
    breakdown: dict[str, str]  # category -> "₹X/month → ₹Y/month"

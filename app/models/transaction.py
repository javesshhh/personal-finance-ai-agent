import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class TransactionCategory(str, enum.Enum):
    FOOD = "food"
    TRANSPORT = "transport"
    SUBSCRIPTIONS = "subscriptions"
    UTILITIES = "utilities"
    ENTERTAINMENT = "entertainment"
    SAVINGS = "savings"
    HEALTHCARE = "healthcare"
    SHOPPING = "shopping"
    INCOME = "income"
    OTHER = "other"

    @classmethod
    def coerce(cls, value: str) -> "TransactionCategory":
        """Convert an arbitrary string to a TransactionCategory, falling back to OTHER."""
        try:
            return cls(value.lower().strip())
        except ValueError:
            return cls.OTHER


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[TransactionCategory] = mapped_column(
        Enum(TransactionCategory), nullable=False, default=TransactionCategory.OTHER
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("date", "description", "amount", name="uq_transaction_date_description_amount"),
    )

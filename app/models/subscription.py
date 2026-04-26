import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    latest_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    previous_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    last_charged: Mapped[date] = mapped_column(Date, nullable=False)
    frequency_days: Mapped[int] = mapped_column(nullable=False)
    waste_score: Mapped[int | None] = mapped_column(nullable=True)
    waste_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    session: Mapped["Session"] = relationship(back_populates="subscriptions")  # noqa: F821

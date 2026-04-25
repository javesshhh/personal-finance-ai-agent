# Phase 04 — Subscription Intelligence Layer

## Overview

This phase builds the subscription detector — the feature that automatically finds recurring charges in your transaction history, tracks price changes, and scores each subscription by perceived waste. This is one of the highest-value features in the demo story.

**Why now:** Transaction data from Phase 03 is the raw material. Phase 04 reads from `transactions` and writes to a new `subscriptions` table, so this is the natural next step.

**What you'll build:**
- `subscriptions` table
- Detection service that scans transactions for recurring patterns
- Price-change detection
- Waste scoring via Claude
- API routes
- MCP tools `audit_subscriptions` and `flag_price_changes`
- Tests

---

## Pros / Cons of Key Decisions

### Decision: Rule-based detection vs. AI-based detection

| | Rule-based (regex + frequency analysis) | AI-based (Claude reads all transactions) |
|---|---|---|
| **Pro** | Fast, cheap, deterministic, testable | More flexible; catches edge cases like Netflix → "NFLX" |
| **Con** | Misses abbreviations and fuzzy matches | Expensive for large histories; slower |
| **Verdict** | ✅ Rule-based with normalized description matching — fast and reliable for 95% of cases. Claude used only for waste scoring, not detection. |

### Decision: Waste score computed on-demand vs. cached

| | On-demand (call Claude at query time) | Cached in DB |
|---|---|---|
| **Pro** | Always fresh | Fast reads; no API call on every request |
| **Con** | Slow read; costly for 20+ subscriptions | Can go stale |
| **Verdict** | ✅ Cached — score is recomputed only when a subscription's transactions change. Score lives in the `subscriptions` table. |

### Decision: Auto-detect on every transaction insert vs. scheduled job

| | On insert trigger | Scheduled job (Celery beat) |
|---|---|---|
| **Pro** | Real-time detection | Batched; cheaper; less DB thrashing |
| **Con** | Slow inserts; complex logic on hot path | Detection lags by job interval |
| **Verdict** | ✅ On-demand: expose a `POST /subscriptions/detect` endpoint the user calls after importing CSV. Perfect for MVP. |

---

## Checklist

### 1. Create the Subscription ORM model

- [ ] Create `app/models/subscription.py`:
  ```python
  from datetime import date
  from decimal import Decimal

  from sqlalchemy import Date, Numeric, String, Text
  from sqlalchemy.orm import Mapped, mapped_column

  from core.database import Base


  class Subscription(Base):
      __tablename__ = "subscriptions"

      id: Mapped[int] = mapped_column(primary_key=True)
      name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
      normalized_pattern: Mapped[str] = mapped_column(String(256), nullable=False)
      latest_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
      previous_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
      last_charged: Mapped[date] = mapped_column(Date, nullable=False)
      frequency_days: Mapped[int] = mapped_column(nullable=False)
      waste_score: Mapped[int | None] = mapped_column(nullable=True)  # 0-100
      waste_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
      is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
  ```
- [ ] Register in `app/models/__init__.py`:
  ```python
  from app.models.subscription import Subscription  # noqa: F401
  ```

---

### 2. Generate and apply migration

- [ ] Generate:
  ```bash
  alembic revision --autogenerate -m "add subscriptions table"
  ```
- [ ] Verify the migration file looks correct, then apply:
  ```bash
  alembic upgrade head
  ```
- [ ] Confirm:
  ```bash
  psql postgresql://finsight:finsight@localhost:5432/finsight -c "\d subscriptions"
  ```

---

### 3. Create Pydantic schemas

- [ ] Create `app/schemas/subscription.py`:
  ```python
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
  ```

---

### 4. Create the subscription detection service

- [ ] Create `app/services/subscription_service.py`:
  ```python
  import re
  from collections import defaultdict
  from datetime import date
  from decimal import Decimal

  from anthropic import AsyncAnthropic
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.subscription import Subscription
  from app.models.transaction import Transaction
  from app.schemas.subscription import PriceChangeAlert, SubscriptionRead
  from core.config import settings

  client = AsyncAnthropic(api_key=settings.anthropic_api_key)

  # Known subscription keywords for fast matching
  SUBSCRIPTION_KEYWORDS = [
      "netflix", "spotify", "amazon prime", "hotstar", "youtube premium",
      "apple", "google", "microsoft", "adobe", "notion", "github",
      "swiggy one", "zomato pro", "jio", "airtel", "vodafone",
      "icloud", "dropbox", "slack", "zoom", "figma",
  ]


  def _normalize(description: str) -> str:
      """Lowercase, strip punctuation, collapse whitespace."""
      return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", description.lower())).strip()


  def _find_pattern(normalized: str) -> str | None:
      """Return the matched keyword if the description contains a known subscription name."""
      for keyword in SUBSCRIPTION_KEYWORDS:
          if keyword in normalized:
              return keyword
      return None


  async def detect_subscriptions(db: AsyncSession) -> list[Subscription]:
      """Scan all transactions and upsert detected subscriptions.

      Groups transactions by subscription keyword, identifies recurring charges,
      and upserts into the subscriptions table.

      Args:
          db: Async database session.

      Returns:
          List of upserted Subscription ORM instances.
      """
      result = await db.execute(
          select(Transaction).where(Transaction.amount < 0).order_by(Transaction.date)
      )
      transactions = result.scalars().all()

      # Group by subscription pattern
      grouped: dict[str, list[Transaction]] = defaultdict(list)
      for t in transactions:
          pattern = _find_pattern(_normalize(t.description))
          if pattern:
              grouped[pattern].append(t)

      upserted: list[Subscription] = []

      for pattern, txns in grouped.items():
          if len(txns) < 2:
              # Only one occurrence — not recurring
              continue

          sorted_txns = sorted(txns, key=lambda t: t.date)
          latest = sorted_txns[-1]
          previous = sorted_txns[-2] if len(sorted_txns) >= 2 else None

          # Estimate frequency from average gap between charges
          gaps = [
              (sorted_txns[i].date - sorted_txns[i - 1].date).days
              for i in range(1, len(sorted_txns))
          ]
          avg_gap = int(sum(gaps) / len(gaps))

          # Check if already exists
          existing = await db.execute(
              select(Subscription).where(Subscription.normalized_pattern == pattern)
          )
          sub = existing.scalar_one_or_none()

          if sub:
              sub.previous_amount = sub.latest_amount
              sub.latest_amount = abs(latest.amount)
              sub.last_charged = latest.date
              sub.frequency_days = avg_gap
              sub.is_active = True
          else:
              sub = Subscription(
                  name=pattern.title(),
                  normalized_pattern=pattern,
                  latest_amount=abs(latest.amount),
                  previous_amount=abs(previous.amount) if previous else None,
                  last_charged=latest.date,
                  frequency_days=avg_gap,
              )
              db.add(sub)

          upserted.append(sub)

      await db.commit()
      for s in upserted:
          await db.refresh(s)

      # Score waste asynchronously
      await _score_waste(db, upserted)
      return upserted


  async def _score_waste(db: AsyncSession, subscriptions: list[Subscription]) -> None:
      """Use Claude to assign a waste score (0-100) to each subscription.

      0 = essential/high-value, 100 = pure waste.
      Updates waste_score and waste_reason on each subscription in place.

      Args:
          db: Async database session.
          subscriptions: List of Subscription instances to score.
      """
      if not subscriptions:
          return

      sub_list = "\n".join(
          [f"- {s.name}: ₹{s.latest_amount}/~{s.frequency_days} days" for s in subscriptions]
      )

      response = await client.messages.create(
          model="claude-sonnet-4-6",
          max_tokens=1024,
          system="""You are a personal finance advisor scoring subscription waste.
  For each subscription, respond with a JSON array of objects with keys: name, score (0-100), reason.
  0 = essential, 100 = likely forgotten/wasteful. Base scores on typical usage patterns.""",
          messages=[{"role": "user", "content": sub_list}],
      )

      import json
      scores: list[dict] = json.loads(response.content[0].text.strip())
      score_map = {s["name"].lower(): s for s in scores}

      for sub in subscriptions:
          entry = score_map.get(sub.name.lower())
          if entry:
              sub.waste_score = entry["score"]
              sub.waste_reason = entry["reason"]

      await db.commit()


  async def get_all_subscriptions(db: AsyncSession) -> list[SubscriptionRead]:
      """Fetch all active subscriptions ordered by waste score descending.

      Args:
          db: Async database session.

      Returns:
          List of SubscriptionRead schemas.
      """
      result = await db.execute(
          select(Subscription)
          .where(Subscription.is_active == True)  # noqa: E712
          .order_by(Subscription.waste_score.desc().nulls_last())
      )
      subs = result.scalars().all()
      return [SubscriptionRead.model_validate(s) for s in subs]


  async def get_price_changes(db: AsyncSession) -> list[PriceChangeAlert]:
      """Return subscriptions where the price has increased since last detection.

      Args:
          db: Async database session.

      Returns:
          List of PriceChangeAlert for subscriptions with increased prices.
      """
      result = await db.execute(
          select(Subscription).where(
              Subscription.previous_amount.is_not(None),
              Subscription.latest_amount > Subscription.previous_amount,
          )
      )
      subs = result.scalars().all()
      return [
          PriceChangeAlert(
              name=s.name,
              previous_amount=s.previous_amount,
              latest_amount=s.latest_amount,
              change_pct=round(float((s.latest_amount - s.previous_amount) / s.previous_amount * 100), 2),
          )
          for s in subs
      ]
  ```

---

### 5. Create API routes

- [ ] Create `api/subscriptions.py`:
  ```python
  from fastapi import APIRouter, Depends
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.schemas.subscription import PriceChangeAlert, SubscriptionRead
  from app.services import subscription_service
  from core.database import get_db

  router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


  @router.post("/detect", response_model=list[SubscriptionRead])
  async def detect_subscriptions(db: AsyncSession = Depends(get_db)) -> list[SubscriptionRead]:
      subs = await subscription_service.detect_subscriptions(db)
      return [SubscriptionRead.model_validate(s) for s in subs]


  @router.get("/", response_model=list[SubscriptionRead])
  async def list_subscriptions(db: AsyncSession = Depends(get_db)) -> list[SubscriptionRead]:
      return await subscription_service.get_all_subscriptions(db)


  @router.get("/price-changes", response_model=list[PriceChangeAlert])
  async def price_changes(db: AsyncSession = Depends(get_db)) -> list[PriceChangeAlert]:
      return await subscription_service.get_price_changes(db)
  ```
- [ ] Register in `core/app.py`:
  ```python
  from api.subscriptions import router as subscriptions_router
  app.include_router(subscriptions_router, prefix="/api/v1")
  ```

---

### 6. Add MCP tools

- [ ] Create `mcp_server/tools/subscriptions.py`:
  ```python
  from mcp.server import Server
  from mcp.types import TextContent

  from app.services import subscription_service
  from core.database import AsyncSessionLocal


  def register_subscription_tools(server: Server) -> None:
      @server.tool()
      async def audit_subscriptions() -> list[TextContent]:
          """List all detected subscriptions with waste scores."""
          async with AsyncSessionLocal() as db:
              subs = await subscription_service.get_all_subscriptions(db)
          if not subs:
              return [TextContent(type="text", text="No subscriptions detected yet. Run /detect first.")]
          lines = [
              f"{s.name}: ₹{s.latest_amount}/~{s.frequency_days}d | "
              f"Waste score: {s.waste_score or 'N/A'}/100 — {s.waste_reason or ''}"
              for s in subs
          ]
          return [TextContent(type="text", text="\n".join(lines))]

      @server.tool()
      async def flag_price_changes() -> list[TextContent]:
          """Detect subscriptions that have increased in price."""
          async with AsyncSessionLocal() as db:
              alerts = await subscription_service.get_price_changes(db)
          if not alerts:
              return [TextContent(type="text", text="No price increases detected.")]
          lines = [
              f"⚠️ {a.name}: ₹{a.previous_amount} → ₹{a.latest_amount} (+{a.change_pct}%)"
              for a in alerts
          ]
          return [TextContent(type="text", text="\n".join(lines))]
  ```
- [ ] Register in `mcp_server/server.py`:
  ```python
  from mcp_server.tools.subscriptions import register_subscription_tools
  register_subscription_tools(server)
  ```

---

### 7. Write tests

- [ ] Create `tests/test_subscription_service.py`:
  ```python
  from datetime import date
  from decimal import Decimal
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest

  from app.models.transaction import Transaction, TransactionCategory


  @pytest.mark.asyncio
  async def test_detect_subscriptions_finds_netflix(db_session):
      # Seed two Netflix transactions
      for d, amount in [(date(2024, 1, 15), Decimal("-649")), (date(2024, 2, 15), Decimal("-649"))]:
          db_session.add(
              Transaction(
                  date=d,
                  description="NETFLIX.COM",
                  amount=amount,
                  category=TransactionCategory.SUBSCRIPTIONS,
              )
          )
      await db_session.commit()

      with patch("app.services.subscription_service._score_waste", new_callable=AsyncMock):
          from app.services import subscription_service
          subs = await subscription_service.detect_subscriptions(db_session)

      assert len(subs) == 1
      assert "netflix" in subs[0].normalized_pattern
      assert subs[0].latest_amount == Decimal("649")


  @pytest.mark.asyncio
  async def test_single_occurrence_not_detected(db_session):
      db_session.add(
          Transaction(
              date=date(2024, 1, 15),
              description="NETFLIX.COM",
              amount=Decimal("-649"),
              category=TransactionCategory.SUBSCRIPTIONS,
          )
      )
      await db_session.commit()

      with patch("app.services.subscription_service._score_waste", new_callable=AsyncMock):
          from app.services import subscription_service
          subs = await subscription_service.detect_subscriptions(db_session)

      assert len(subs) == 0
  ```
- [ ] Run tests:
  ```bash
  pytest tests/test_subscription_service.py -v
  ```

---

## Verification — Phase 04 Complete

- [ ] `alembic current` → shows subscriptions migration applied
- [ ] Import a CSV with Netflix/Spotify transactions, then call `POST /api/v1/subscriptions/detect` → returns detected subscriptions with waste scores
- [ ] `GET /api/v1/subscriptions/price-changes` → returns alerts for price-increased subs
- [ ] `pytest tests/test_subscription_service.py -v` → all tests pass
- [ ] `ruff check .` → no errors
- [ ] Commit:
  ```bash
  git add -A
  git commit -m "feat(subscriptions): add subscription detection, waste scoring, and price change alerts"
  ```

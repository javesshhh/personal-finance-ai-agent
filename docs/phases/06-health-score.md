# Phase 06 — Proactive Financial Health Score

## Overview

The health score is a weekly 0–100 metric that summarizes your financial fitness across four dimensions:
- **Savings rate** — what % of income went to savings
- **Budget adherence** — how well you stayed within category budgets
- **Subscription waste** — how much money is going to low-value subscriptions
- **Unusual spends** — any anomalous transactions this week

A Celery beat job runs this computation every Sunday, stores the result, and writes a digest. The score is also queryable on-demand via MCP.

**Why now:** This phase uses data from transactions (Phase 03), subscriptions (Phase 04), and will reference budgets (Phase 07). It's positioned here because subscriptions are now available and budgets will come next — you can compute a partial score now and enhance it in Phase 07.

---

## Pros / Cons of Key Decisions

### Decision: Score computed in Python vs. delegated entirely to Claude

| | Python computation + Claude narrative | Claude computes everything |
|---|---|---|
| **Pro** | Deterministic, testable score; Claude adds only the insight layer | Single integration point |
| **Con** | More code | Non-deterministic score; can't write unit tests for the number |
| **Verdict** | ✅ Python computes the score from real data; Claude writes the weekly digest narrative only |

### Decision: Store one score per week vs. rolling score

| | One row per week | Rolling daily score |
|---|---|---|
| **Pro** | Simple; matches the "weekly digest" mental model | Fine-grained history |
| **Con** | Less granular | More storage; more complex aggregation |
| **Verdict** | ✅ One row per week — ISO week number as the key |

### Decision: Celery beat schedule vs. cron tab

| | Celery beat | System cron |
|---|---|---|
| **Pro** | Managed in Python; respects app config; no OS config | Simple, no Celery overhead |
| **Con** | Requires Celery beat worker running | External to the app; no Python config |
| **Verdict** | ✅ Celery beat — keeps everything in the app |

---

## Checklist

### 1. Create the HealthScore ORM model

- [ ] Create `app/models/health_score.py`:
  ```python
  from sqlalchemy import Text
  from sqlalchemy.orm import Mapped, mapped_column

  from core.database import Base


  class HealthScore(Base):
      __tablename__ = "health_scores"

      id: Mapped[int] = mapped_column(primary_key=True)
      year: Mapped[int] = mapped_column(nullable=False)
      week: Mapped[int] = mapped_column(nullable=False)
      score: Mapped[int] = mapped_column(nullable=False)  # 0-100

      # Component scores
      savings_rate_score: Mapped[int] = mapped_column(nullable=False)
      budget_adherence_score: Mapped[int] = mapped_column(nullable=False)
      subscription_waste_score: Mapped[int] = mapped_column(nullable=False)
      unusual_spend_score: Mapped[int] = mapped_column(nullable=False)

      digest: Mapped[str | None] = mapped_column(Text, nullable=True)

      __table_args__ = (
          # Only one score per year+week
          {"schema": None},
      )
  ```
- [ ] Add a unique constraint on `(year, week)` — update the model's `__table_args__`:
  ```python
  from sqlalchemy import UniqueConstraint
  __table_args__ = (UniqueConstraint("year", "week", name="uq_health_score_year_week"),)
  ```
- [ ] Register in `app/models/__init__.py`:
  ```python
  from app.models.health_score import HealthScore  # noqa: F401
  ```

---

### 2. Generate and apply migration

- [ ] Generate:
  ```bash
  alembic revision --autogenerate -m "add health_scores table"
  ```
- [ ] Verify and apply:
  ```bash
  alembic upgrade head
  ```

---

### 3. Create Pydantic schemas

- [ ] Create `app/schemas/health_score.py`:
  ```python
  from pydantic import BaseModel


  class HealthScoreRead(BaseModel):
      model_config = {"from_attributes": True}

      id: int
      year: int
      week: int
      score: int
      savings_rate_score: int
      budget_adherence_score: int
      subscription_waste_score: int
      unusual_spend_score: int
      digest: str | None
  ```

---

### 4. Create the scoring service

- [ ] Create `app/services/health_score_service.py`:
  ```python
  import json
  from datetime import date, timedelta
  from decimal import Decimal

  from anthropic import AsyncAnthropic
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.health_score import HealthScore
  from app.models.subscription import Subscription
  from app.models.transaction import Transaction, TransactionCategory
  from app.schemas.health_score import HealthScoreRead
  from core.config import settings

  client = AsyncAnthropic(api_key=settings.anthropic_api_key)

  WEIGHTS = {
      "savings_rate": 0.35,
      "budget_adherence": 0.30,
      "subscription_waste": 0.20,
      "unusual_spend": 0.15,
  }


  async def _compute_savings_rate_score(db: AsyncSession, start: date, end: date) -> int:
      """Score savings rate: 100 = saved >20% of income, 0 = no savings detected."""
      result = await db.execute(
          select(Transaction).where(
              Transaction.date >= start,
              Transaction.date <= end,
              Transaction.category == TransactionCategory.SAVINGS,
          )
      )
      savings_txns = result.scalars().all()
      total_saved = sum(abs(t.amount) for t in savings_txns)

      income_result = await db.execute(
          select(Transaction).where(
              Transaction.date >= start,
              Transaction.date <= end,
              Transaction.amount > 0,
          )
      )
      income_txns = income_result.scalars().all()
      total_income = sum(t.amount for t in income_txns)

      if total_income == 0:
          return 50  # No income data — neutral score
      rate = float(total_saved / total_income)
      return min(100, int(rate / 0.20 * 100))


  async def _compute_subscription_waste_score(db: AsyncSession) -> int:
      """Score 100 = no waste, 0 = all subscriptions are waste-scored high."""
      result = await db.execute(
          select(Subscription).where(
              Subscription.is_active == True,  # noqa: E712
              Subscription.waste_score.is_not(None),
          )
      )
      subs = result.scalars().all()
      if not subs:
          return 80  # No subscriptions — mostly good
      avg_waste = sum(s.waste_score for s in subs) / len(subs)
      return max(0, 100 - int(avg_waste))


  async def _compute_unusual_spend_score(db: AsyncSession, start: date, end: date) -> int:
      """Score based on whether any single transaction is >3x the category average."""
      result = await db.execute(
          select(Transaction).where(
              Transaction.date >= start,
              Transaction.date <= end,
              Transaction.amount < 0,
          )
      )
      txns = result.scalars().all()

      if not txns:
          return 100

      # Group by category
      by_category: dict = {}
      for t in txns:
          by_category.setdefault(t.category, []).append(abs(t.amount))

      anomalies = 0
      for amounts in by_category.values():
          avg = sum(amounts) / len(amounts)
          for a in amounts:
              if a > avg * 3:
                  anomalies += 1

      return max(0, 100 - (anomalies * 15))


  async def generate_weekly_score(db: AsyncSession, target_date: date | None = None) -> HealthScore:
      """Generate and persist the financial health score for the week containing target_date.

      Computes component scores, calculates a weighted total, and generates a Claude digest.
      Upserts (updates if week already scored).

      Args:
          db: Async database session.
          target_date: Date within the target week. Defaults to today.

      Returns:
          Persisted HealthScore ORM instance.
      """
      if target_date is None:
          target_date = date.today()

      # Get ISO week boundaries (Monday to Sunday)
      week_start = target_date - timedelta(days=target_date.weekday())
      week_end = week_start + timedelta(days=6)
      iso_year, iso_week, _ = target_date.isocalendar()

      savings_score = await _compute_savings_rate_score(db, week_start, week_end)
      waste_score = await _compute_subscription_waste_score(db)
      unusual_score = await _compute_unusual_spend_score(db, week_start, week_end)
      budget_score = 70  # Placeholder until Phase 07 adds budget data

      total_score = int(
          savings_score * WEIGHTS["savings_rate"]
          + budget_score * WEIGHTS["budget_adherence"]
          + waste_score * WEIGHTS["subscription_waste"]
          + unusual_score * WEIGHTS["unusual_spend"]
      )

      # Generate digest narrative
      digest = await _generate_digest(total_score, savings_score, budget_score, waste_score, unusual_score)

      # Upsert
      existing = await db.execute(
          select(HealthScore).where(HealthScore.year == iso_year, HealthScore.week == iso_week)
      )
      record = existing.scalar_one_or_none()

      if record:
          record.score = total_score
          record.savings_rate_score = savings_score
          record.budget_adherence_score = budget_score
          record.subscription_waste_score = waste_score
          record.unusual_spend_score = unusual_score
          record.digest = digest
      else:
          record = HealthScore(
              year=iso_year,
              week=iso_week,
              score=total_score,
              savings_rate_score=savings_score,
              budget_adherence_score=budget_score,
              subscription_waste_score=waste_score,
              unusual_spend_score=unusual_score,
              digest=digest,
          )
          db.add(record)

      await db.commit()
      await db.refresh(record)
      return record


  async def _generate_digest(
      total: int,
      savings: int,
      budget: int,
      waste: int,
      unusual: int,
  ) -> str:
      """Use Claude to generate a 3-sentence weekly financial digest.

      Args:
          total: Overall health score.
          savings: Savings rate component score.
          budget: Budget adherence component score.
          waste: Subscription waste component score.
          unusual: Unusual spend component score.

      Returns:
          A 3-sentence narrative digest string.
      """
      data = {
          "overall_score": total,
          "savings_rate_score": savings,
          "budget_adherence_score": budget,
          "subscription_waste_score": waste,
          "unusual_spend_score": unusual,
      }

      response = await client.messages.create(
          model="claude-sonnet-4-6",
          max_tokens=256,
          system="""You are a supportive personal finance coach writing a weekly digest.
  Write exactly 3 sentences: one celebrating a strength, one noting the biggest opportunity, one actionable tip.
  Be specific and warm, not generic. Use the scores to determine tone.""",
          messages=[{"role": "user", "content": json.dumps(data)}],
      )
      return response.content[0].text.strip()


  async def get_latest_score(db: AsyncSession) -> HealthScoreRead | None:
      """Fetch the most recent health score.

      Args:
          db: Async database session.

      Returns:
          Most recent HealthScoreRead, or None if no score has been generated yet.
      """
      result = await db.execute(
          select(HealthScore).order_by(HealthScore.year.desc(), HealthScore.week.desc()).limit(1)
      )
      record = result.scalar_one_or_none()
      return HealthScoreRead.model_validate(record) if record else None
  ```

---

### 5. Wire up the Celery task

- [ ] Replace the placeholder in `celery_tasks/health_score.py`:
  ```python
  import asyncio
  from datetime import date

  from core.celery_app import celery_app
  from core.database import AsyncSessionLocal


  @celery_app.task(name="generate_health_score")
  def generate_health_score_task() -> dict:
      """Celery task: generate and persist this week's health score."""
      async def _run():
          from app.services.health_score_service import generate_weekly_score
          async with AsyncSessionLocal() as db:
              score = await generate_weekly_score(db)
          return {"score": score.score, "week": score.week, "year": score.year}

      return asyncio.run(_run())
  ```
- [ ] Add the weekly beat schedule to `core/celery_app.py`:
  ```python
  from celery.schedules import crontab

  celery_app.conf.beat_schedule = {
      "weekly-health-score": {
          "task": "generate_health_score",
          "schedule": crontab(hour=8, minute=0, day_of_week="monday"),  # Every Monday 8am UTC
      },
  }
  ```
- [ ] Start Celery beat (in a separate terminal):
  ```bash
  celery -A core.celery_app.celery_app beat --loglevel=info
  ```

---

### 6. Create API route

- [ ] Create `api/health_score.py`:
  ```python
  from fastapi import APIRouter, Depends, HTTPException
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.schemas.health_score import HealthScoreRead
  from app.services import health_score_service
  from core.database import get_db

  router = APIRouter(prefix="/health-score", tags=["health-score"])


  @router.post("/generate", response_model=HealthScoreRead)
  async def generate_score(db: AsyncSession = Depends(get_db)) -> HealthScoreRead:
      """Manually trigger health score generation for the current week."""
      score = await health_score_service.generate_weekly_score(db)
      return HealthScoreRead.model_validate(score)


  @router.get("/", response_model=HealthScoreRead)
  async def get_latest(db: AsyncSession = Depends(get_db)) -> HealthScoreRead:
      score = await health_score_service.get_latest_score(db)
      if not score:
          raise HTTPException(status_code=404, detail="No health score generated yet. Call POST /generate first.")
      return score
  ```
- [ ] Register in `core/app.py`:
  ```python
  from api.health_score import router as health_score_router
  app.include_router(health_score_router, prefix="/api/v1")
  ```

---

### 7. Add MCP tool `get_health_score`

- [ ] Create `mcp_server/tools/health_score.py`:
  ```python
  from mcp.server import Server
  from mcp.types import TextContent

  from app.services import health_score_service
  from core.database import AsyncSessionLocal


  def register_health_score_tools(server: Server) -> None:
      @server.tool()
      async def get_health_score() -> list[TextContent]:
          """Get the current financial health score with breakdown and weekly digest."""
          async with AsyncSessionLocal() as db:
              score = await health_score_service.get_latest_score(db)

          if not score:
              return [TextContent(type="text", text="No health score yet. Generate one via POST /api/v1/health-score/generate")]

          lines = [
              f"📊 Financial Health Score: {score.score}/100 (Week {score.week}, {score.year})",
              f"  💰 Savings Rate:        {score.savings_rate_score}/100",
              f"  📋 Budget Adherence:    {score.budget_adherence_score}/100",
              f"  🔄 Subscription Waste:  {score.subscription_waste_score}/100",
              f"  ⚠️  Unusual Spends:      {score.unusual_spend_score}/100",
              f"\n{score.digest or 'No digest available.'}",
          ]
          return [TextContent(type="text", text="\n".join(lines))]
  ```
- [ ] Register in `mcp_server/server.py`:
  ```python
  from mcp_server.tools.health_score import register_health_score_tools
  register_health_score_tools(server)
  ```

---

### 8. Write tests

- [ ] Create `tests/test_health_score_service.py`:
  ```python
  from datetime import date
  from decimal import Decimal
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest

  from app.models.transaction import Transaction, TransactionCategory


  @pytest.mark.asyncio
  async def test_generate_weekly_score_persists(db_session):
      mock_digest = MagicMock()
      mock_digest.content = [MagicMock(text="Great savings this week! Watch your food spend. Try meal prepping Sundays.")]

      with patch("app.services.health_score_service.client") as mock_client:
          mock_client.messages.create = AsyncMock(return_value=mock_digest)
          from app.services import health_score_service
          score = await health_score_service.generate_weekly_score(db_session, date(2024, 1, 15))

      assert score.id is not None
      assert 0 <= score.score <= 100
      assert score.digest is not None


  @pytest.mark.asyncio
  async def test_generate_weekly_score_upserts(db_session):
      """Calling generate twice for same week updates rather than inserts."""
      mock_digest = MagicMock()
      mock_digest.content = [MagicMock(text="Weekly digest.")]

      with patch("app.services.health_score_service.client") as mock_client:
          mock_client.messages.create = AsyncMock(return_value=mock_digest)
          from app.services import health_score_service
          score1 = await health_score_service.generate_weekly_score(db_session, date(2024, 1, 15))
          score2 = await health_score_service.generate_weekly_score(db_session, date(2024, 1, 15))

      assert score1.id == score2.id
  ```
- [ ] Run tests:
  ```bash
  pytest tests/test_health_score_service.py -v
  ```

---

## Verification — Phase 06 Complete

- [ ] `POST /api/v1/health-score/generate` → returns a score with all 4 components and a digest
- [ ] `GET /api/v1/health-score/` → returns the same score
- [ ] `celery -A core.celery_app.celery_app worker --loglevel=info` → starts without error
- [ ] `pytest tests/test_health_score_service.py -v` → all tests pass
- [ ] `ruff check .` → no errors
- [ ] Commit:
  ```bash
  git add -A
  git commit -m "feat(health-score): add weekly financial health score with Celery beat job and Claude digest"
  ```

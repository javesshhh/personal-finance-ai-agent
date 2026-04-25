# Phase 07 — Budget & Goal Tracking

## Overview

This phase adds structured budget and goal tracking:
- **Budgets**: Set a monthly spending cap per category. The health score uses these in Phase 06's budget adherence component.
- **Goals**: Set a savings target with a deadline (e.g., "Emergency Fund: ₹1,00,000 by Dec 2024"). AI tracks progress.

After this phase, the health score's `budget_adherence_score` will be real (replacing the placeholder 70).

---

## Pros / Cons of Key Decisions

### Decision: One budget row per category per month vs. a single monthly budget with category breakdown

| | One row per category per month | Single row with JSON breakdown |
|---|---|---|
| **Pro** | Normalized, queryable, easy to aggregate | Simpler schema |
| **Con** | More rows | Hard to query individual categories; not SQL-friendly |
| **Verdict** | ✅ One row per category per month — proper normalization |

### Decision: Goal progress computed in SQL vs. Python

| | SQL aggregation | Python loop |
|---|---|---|
| **Pro** | Fast, single query | Readable, easy to test |
| **Con** | Complex SQL | N+1 if not careful |
| **Verdict** | ✅ SQL aggregation — `SUM(amount)` filtered by savings category is a single query, not worth pulling into Python |

### Decision: Alert on budget overrun in API response vs. separate alert endpoint

| | Inline in GET /budgets response | Separate /alerts endpoint |
|---|---|---|
| **Pro** | Simpler; one call gets everything | Separation of concerns |
| **Con** | Mixed concerns in one response | Extra endpoint to build |
| **Verdict** | ✅ Inline — add an `is_over_budget: bool` and `spent: Decimal` field to the budget read schema |

---

## Checklist

### 1. Create the Budget ORM model

- [ ] Create `app/models/budget.py`:
  ```python
  from decimal import Decimal

  from sqlalchemy import Enum, Numeric, UniqueConstraint
  from sqlalchemy.orm import Mapped, mapped_column

  from app.models.transaction import TransactionCategory
  from core.database import Base


  class Budget(Base):
      __tablename__ = "budgets"

      id: Mapped[int] = mapped_column(primary_key=True)
      category: Mapped[TransactionCategory] = mapped_column(Enum(TransactionCategory), nullable=False)
      month: Mapped[int] = mapped_column(nullable=False)  # 1-12
      year: Mapped[int] = mapped_column(nullable=False)
      limit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

      __table_args__ = (
          UniqueConstraint("category", "month", "year", name="uq_budget_category_month_year"),
      )
  ```
- [ ] Register in `app/models/__init__.py`:
  ```python
  from app.models.budget import Budget  # noqa: F401
  ```

---

### 2. Create the Goal ORM model

- [ ] Create `app/models/goal.py`:
  ```python
  from datetime import date
  from decimal import Decimal

  from sqlalchemy import Date, Numeric, String
  from sqlalchemy.orm import Mapped, mapped_column

  from core.database import Base


  class Goal(Base):
      __tablename__ = "goals"

      id: Mapped[int] = mapped_column(primary_key=True)
      name: Mapped[str] = mapped_column(String(256), nullable=False)
      target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
      deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
      is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
  ```
- [ ] Register in `app/models/__init__.py`:
  ```python
  from app.models.goal import Goal  # noqa: F401
  ```

---

### 3. Generate and apply migration

- [ ] Generate:
  ```bash
  alembic revision --autogenerate -m "add budgets and goals tables"
  ```
- [ ] Verify and apply:
  ```bash
  alembic upgrade head
  ```

---

### 4. Create Pydantic schemas

- [ ] Create `app/schemas/budget.py`:
  ```python
  from decimal import Decimal

  from pydantic import BaseModel, field_validator

  from app.models.transaction import TransactionCategory


  class BudgetCreate(BaseModel):
      category: TransactionCategory
      month: int
      year: int
      limit_amount: Decimal

      @field_validator("month")
      @classmethod
      def month_must_be_valid(cls, v: int) -> int:
          if not (1 <= v <= 12):
              raise ValueError("month must be between 1 and 12")
          return v

      @field_validator("limit_amount")
      @classmethod
      def limit_must_be_positive(cls, v: Decimal) -> Decimal:
          if v <= 0:
              raise ValueError("limit_amount must be positive")
          return v


  class BudgetRead(BaseModel):
      model_config = {"from_attributes": True}

      id: int
      category: TransactionCategory
      month: int
      year: int
      limit_amount: Decimal
      spent: Decimal = Decimal("0")
      is_over_budget: bool = False
  ```
- [ ] Create `app/schemas/goal.py`:
  ```python
  from datetime import date
  from decimal import Decimal

  from pydantic import BaseModel, field_validator


  class GoalCreate(BaseModel):
      name: str
      target_amount: Decimal
      deadline: date | None = None

      @field_validator("target_amount")
      @classmethod
      def amount_must_be_positive(cls, v: Decimal) -> Decimal:
          if v <= 0:
              raise ValueError("target_amount must be positive")
          return v


  class GoalRead(BaseModel):
      model_config = {"from_attributes": True}

      id: int
      name: str
      target_amount: Decimal
      deadline: date | None
      is_active: bool
      saved_so_far: Decimal = Decimal("0")
      progress_pct: float = 0.0
      months_remaining: int | None = None
  ```

---

### 5. Create the budget service

- [ ] Create `app/services/budget_service.py`:
  ```python
  from datetime import date
  from decimal import Decimal

  from sqlalchemy import extract, func, select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.budget import Budget
  from app.models.transaction import Transaction
  from app.schemas.budget import BudgetCreate, BudgetRead
  from core.database import Base


  async def upsert_budget(db: AsyncSession, data: BudgetCreate) -> BudgetRead:
      """Create or update a budget for a category/month/year combination.

      Args:
          db: Async database session.
          data: Budget parameters.

      Returns:
          BudgetRead with current spend and over-budget flag populated.
      """
      existing = await db.execute(
          select(Budget).where(
              Budget.category == data.category,
              Budget.month == data.month,
              Budget.year == data.year,
          )
      )
      budget = existing.scalar_one_or_none()

      if budget:
          budget.limit_amount = data.limit_amount
      else:
          budget = Budget(**data.model_dump())
          db.add(budget)

      await db.commit()
      await db.refresh(budget)
      return await _enrich_budget(db, budget)


  async def get_budgets(db: AsyncSession, month: int, year: int) -> list[BudgetRead]:
      """Get all budgets for a month with actual spend populated.

      Args:
          db: Async database session.
          month: Month number (1-12).
          year: Calendar year.

      Returns:
          List of BudgetRead with spent and is_over_budget populated.
      """
      result = await db.execute(select(Budget).where(Budget.month == month, Budget.year == year))
      budgets = result.scalars().all()
      return [await _enrich_budget(db, b) for b in budgets]


  async def _enrich_budget(db: AsyncSession, budget: Budget) -> BudgetRead:
      """Attach actual spend and over-budget flag to a budget."""
      result = await db.execute(
          select(func.sum(Transaction.amount).label("total")).where(
              Transaction.category == budget.category,
              extract("month", Transaction.date) == budget.month,
              extract("year", Transaction.date) == budget.year,
              Transaction.amount < 0,
          )
      )
      spent = abs(result.scalar_one_or_none() or Decimal("0"))
      read = BudgetRead.model_validate(budget)
      read.spent = spent
      read.is_over_budget = spent > budget.limit_amount
      return read


  async def compute_budget_adherence_score(db: AsyncSession, month: int, year: int) -> int:
      """Compute budget adherence score (0-100) for health score component.

      100 = all categories within budget, 0 = all categories over budget.

      Args:
          db: Async database session.
          month: Month to score.
          year: Year to score.

      Returns:
          Integer score 0-100.
      """
      budgets = await get_budgets(db, month, year)
      if not budgets:
          return 70  # Neutral if no budgets set
      over_count = sum(1 for b in budgets if b.is_over_budget)
      return max(0, 100 - int(over_count / len(budgets) * 100))
  ```

---

### 6. Create the goal service

- [ ] Create `app/services/goal_service.py`:
  ```python
  from datetime import date
  from decimal import Decimal

  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.goal import Goal
  from app.models.transaction import Transaction, TransactionCategory
  from app.schemas.goal import GoalCreate, GoalRead


  async def create_goal(db: AsyncSession, data: GoalCreate) -> GoalRead:
      """Persist a new savings goal.

      Args:
          db: Async database session.
          data: Goal parameters.

      Returns:
          GoalRead with progress populated.
      """
      goal = Goal(**data.model_dump())
      db.add(goal)
      await db.commit()
      await db.refresh(goal)
      return await _enrich_goal(db, goal)


  async def get_goals(db: AsyncSession) -> list[GoalRead]:
      """Fetch all active goals with progress populated.

      Args:
          db: Async database session.

      Returns:
          List of GoalRead with saved_so_far, progress_pct, and months_remaining.
      """
      result = await db.execute(select(Goal).where(Goal.is_active == True))  # noqa: E712
      goals = result.scalars().all()
      return [await _enrich_goal(db, g) for g in goals]


  async def _enrich_goal(db: AsyncSession, goal: Goal) -> GoalRead:
      """Compute savings progress from all SAVINGS transactions."""
      from sqlalchemy import func
      result = await db.execute(
          select(func.sum(Transaction.amount).label("total")).where(
              Transaction.category == TransactionCategory.SAVINGS,
              Transaction.amount < 0,
          )
      )
      saved = abs(result.scalar_one_or_none() or Decimal("0"))
      progress_pct = min(100.0, float(saved / goal.target_amount * 100)) if goal.target_amount else 0.0

      months_remaining = None
      if goal.deadline:
          today = date.today()
          months_remaining = max(
              0,
              (goal.deadline.year - today.year) * 12 + (goal.deadline.month - today.month),
          )

      read = GoalRead.model_validate(goal)
      read.saved_so_far = saved
      read.progress_pct = round(progress_pct, 2)
      read.months_remaining = months_remaining
      return read
  ```

---

### 7. Create API routes

- [ ] Create `api/budgets.py`:
  ```python
  from fastapi import APIRouter, Depends
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.schemas.budget import BudgetCreate, BudgetRead
  from app.services import budget_service
  from core.database import get_db

  router = APIRouter(prefix="/budgets", tags=["budgets"])


  @router.post("/", response_model=BudgetRead)
  async def upsert_budget(data: BudgetCreate, db: AsyncSession = Depends(get_db)) -> BudgetRead:
      return await budget_service.upsert_budget(db, data)


  @router.get("/", response_model=list[BudgetRead])
  async def list_budgets(month: int, year: int, db: AsyncSession = Depends(get_db)) -> list[BudgetRead]:
      return await budget_service.get_budgets(db, month, year)
  ```
- [ ] Create `api/goals.py`:
  ```python
  from fastapi import APIRouter, Depends
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.schemas.goal import GoalCreate, GoalRead
  from app.services import goal_service
  from core.database import get_db

  router = APIRouter(prefix="/goals", tags=["goals"])


  @router.post("/", response_model=GoalRead, status_code=201)
  async def create_goal(data: GoalCreate, db: AsyncSession = Depends(get_db)) -> GoalRead:
      return await goal_service.create_goal(db, data)


  @router.get("/", response_model=list[GoalRead])
  async def list_goals(db: AsyncSession = Depends(get_db)) -> list[GoalRead]:
      return await goal_service.get_goals(db)
  ```
- [ ] Register both in `core/app.py`:
  ```python
  from api.budgets import router as budgets_router
  from api.goals import router as goals_router
  app.include_router(budgets_router, prefix="/api/v1")
  app.include_router(goals_router, prefix="/api/v1")
  ```

---

### 8. Update health score to use real budget adherence

- [ ] In `app/services/health_score_service.py`, replace the placeholder:
  ```python
  # Replace:
  budget_score = 70  # Placeholder until Phase 07 adds budget data

  # With:
  from app.services.budget_service import compute_budget_adherence_score
  budget_score = await compute_budget_adherence_score(db, week_start.month, week_start.year)
  ```

---

### 9. Add MCP tools `set_goal` and `get_goals`

- [ ] Create `mcp_server/tools/goals.py`:
  ```python
  from mcp.server import Server
  from mcp.types import TextContent

  from app.schemas.goal import GoalCreate
  from app.services import goal_service
  from core.database import AsyncSessionLocal


  def register_goal_tools(server: Server) -> None:
      @server.tool()
      async def set_goal(name: str, target_amount: float, deadline: str | None = None) -> list[TextContent]:
          """Create a savings goal. deadline format: YYYY-MM-DD (optional)."""
          from datetime import date
          from decimal import Decimal
          data = GoalCreate(
              name=name,
              target_amount=Decimal(str(target_amount)),
              deadline=date.fromisoformat(deadline) if deadline else None,
          )
          async with AsyncSessionLocal() as db:
              goal = await goal_service.create_goal(db, data)
          return [TextContent(type="text", text=f"✅ Goal '{goal.name}' created: ₹{goal.target_amount:,.0f} by {goal.deadline or 'no deadline'}")]

      @server.tool()
      async def get_goals() -> list[TextContent]:
          """List all active savings goals with progress."""
          async with AsyncSessionLocal() as db:
              goals = await goal_service.get_goals(db)
          if not goals:
              return [TextContent(type="text", text="No active goals. Use set_goal to create one.")]
          lines = [
              f"🎯 {g.name}: ₹{g.saved_so_far:,.0f} / ₹{g.target_amount:,.0f} "
              f"({g.progress_pct:.1f}%) — {g.months_remaining or '?'} months left"
              for g in goals
          ]
          return [TextContent(type="text", text="\n".join(lines))]
  ```
- [ ] Register in `mcp_server/server.py`:
  ```python
  from mcp_server.tools.goals import register_goal_tools
  register_goal_tools(server)
  ```

---

### 10. Write tests

- [ ] Create `tests/test_budget_service.py`:
  ```python
  from decimal import Decimal
  import pytest
  from app.models.transaction import TransactionCategory
  from app.schemas.budget import BudgetCreate


  @pytest.mark.asyncio
  async def test_upsert_budget_creates(db_session):
      from app.services import budget_service
      data = BudgetCreate(category=TransactionCategory.FOOD, month=1, year=2024, limit_amount=Decimal("5000"))
      budget = await budget_service.upsert_budget(db_session, data)
      assert budget.id is not None
      assert budget.limit_amount == Decimal("5000")
      assert budget.is_over_budget is False


  @pytest.mark.asyncio
  async def test_upsert_budget_updates_existing(db_session):
      from app.services import budget_service
      data = BudgetCreate(category=TransactionCategory.FOOD, month=2, year=2024, limit_amount=Decimal("5000"))
      b1 = await budget_service.upsert_budget(db_session, data)
      data.limit_amount = Decimal("7000")
      b2 = await budget_service.upsert_budget(db_session, data)
      assert b1.id == b2.id
      assert b2.limit_amount == Decimal("7000")
  ```
- [ ] Run tests:
  ```bash
  pytest tests/test_budget_service.py -v
  ```

---

## Verification — Phase 07 Complete

- [ ] `POST /api/v1/budgets/` with food category → returns budget with `spent` and `is_over_budget`
- [ ] `GET /api/v1/budgets/?month=1&year=2024` → returns all budgets for that month
- [ ] `POST /api/v1/goals/` → creates goal
- [ ] `GET /api/v1/goals/` → returns goals with `saved_so_far` and `progress_pct`
- [ ] Regenerate health score (`POST /api/v1/health-score/generate`) — `budget_adherence_score` is now real
- [ ] `pytest tests/test_budget_service.py -v` → all tests pass
- [ ] `ruff check .` → no errors
- [ ] Commit:
  ```bash
  git add -A
  git commit -m "feat(budgets-goals): add budget tracking, goal progress, and MCP tools set_goal/get_goals"
  ```

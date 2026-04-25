# Phase 05 — "What-If" Scenario Engine

## Overview

The scenario engine is the crown jewel of the demo story. It lets Claude answer questions like:
- *"If I cut food delivery by 50%, when can I afford a MacBook Pro?"*
- *"If I save ₹5000 extra/month, when do I hit my emergency fund goal?"*

This phase builds the simulation service, which feeds real spending data plus a hypothesis to Claude, which runs the projection and returns a structured answer.

**Why now:** This is a read-only feature — it queries existing transaction data (Phase 03) and optionally goals (Phase 07). Doing it now means the demo story is demo-able after just 5 phases.

---

## Pros / Cons of Key Decisions

### Decision: Claude does the math vs. deterministic Python simulation

| | Claude computes projection | Python simulation |
|---|---|---|
| **Pro** | Handles natural language inputs; flexible; explains reasoning | Deterministic, testable, cheap |
| **Con** | Non-deterministic; can hallucinate numbers; expensive per query | Requires parsing structured inputs; no natural language |
| **Verdict** | ✅ Hybrid — Python computes the real spending baseline from DB, Claude receives structured numbers and does the projection + narrative. Best of both. |

### Decision: Store scenario results vs. compute on demand

| | Stored | On demand |
|---|---|---|
| **Pro** | Fast re-reads; history of past scenarios | Simple, no extra table |
| **Con** | Stale if spending data changes; extra schema complexity | Slower; API cost per query |
| **Verdict** | ✅ On demand for MVP — scenarios are exploratory by nature and rarely repeated identically. |

### Decision: Free-text hypothesis vs. structured input

| | Free text ("cut food by 50%") | Structured (`{category: food, reduction_pct: 50}`) |
|---|---|---|
| **Pro** | Natural, easy to use from Claude Desktop | Reliable parsing, testable |
| **Con** | Must be parsed by Claude; ambiguous | Less natural |
| **Verdict** | ✅ Structured input to the API/service; free-text description is Claude Desktop's job — MCP tool accepts natural language and extracts structure |

---

## Checklist

### 1. Create Pydantic schemas for scenario input/output

- [ ] Create `app/schemas/scenario.py`:
  ```python
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
  ```

---

### 2. Create the scenario service

- [ ] Create `app/services/scenario_service.py`:
  ```python
  import json
  from datetime import date, timedelta
  from decimal import Decimal

  from anthropic import AsyncAnthropic
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.schemas.scenario import ScenarioRequest, ScenarioResult
  from app.services.transaction_service import get_spending_by_category
  from core.config import settings

  client = AsyncAnthropic(api_key=settings.anthropic_api_key)


  async def run_scenario(db: AsyncSession, request: ScenarioRequest) -> ScenarioResult:
      """Run a what-if financial scenario using real spending data and Claude projections.

      Computes the current monthly average spending baseline from the last 3 months,
      applies the requested spending changes, and asks Claude to project the time to goal.

      Args:
          db: Async database session.
          request: Scenario parameters including spending changes, target amount, and description.

      Returns:
          ScenarioResult with months to goal, projected savings, and a narrative.
      """
      # Get last 3 months of spending for baseline
      today = date.today()
      three_months_ago = today - timedelta(days=90)
      spending = await get_spending_by_category(db, three_months_ago, today)

      # Build monthly averages (divide by 3)
      monthly_avg = {s.category: s.total / 3 for s in spending}

      # Apply spending changes
      breakdown: dict[str, str] = {}
      total_reduction = Decimal("0")

      for change in request.spending_changes:
          current = monthly_avg.get(change.category, Decimal("0"))
          reduction = current * Decimal(str(change.reduction_pct / 100))
          new_amount = current - reduction
          breakdown[change.category.value] = f"₹{current:,.0f}/month → ₹{new_amount:,.0f}/month"
          total_reduction += reduction

      projected_monthly_savings = total_reduction + request.extra_monthly_savings

      # Ask Claude to contextualize and narrate
      prompt_data = {
          "target": request.target_description,
          "target_amount": float(request.target_amount),
          "projected_monthly_savings": float(projected_monthly_savings),
          "spending_changes": {k: v for k, v in breakdown.items()},
          "extra_savings": float(request.extra_monthly_savings),
      }

      response = await client.messages.create(
          model="claude-sonnet-4-6",
          max_tokens=512,
          system="""You are a personal finance advisor.
  Given spending change data, calculate months to goal and write a motivating 2-sentence narrative.
  Respond ONLY with valid JSON: {"months_to_goal": int_or_null, "narrative": "string"}
  If projected_monthly_savings <= 0, set months_to_goal to null.""",
          messages=[{"role": "user", "content": json.dumps(prompt_data)}],
      )

      result_raw = json.loads(response.content[0].text.strip())
      months = result_raw.get("months_to_goal")
      narrative = result_raw.get("narrative", "")

      return ScenarioResult(
          months_to_goal=months,
          projected_monthly_savings=projected_monthly_savings,
          current_monthly_savings=Decimal("0"),  # Can be enhanced with income tracking later
          narrative=narrative,
          breakdown=breakdown,
      )
  ```

---

### 3. Create API route

- [ ] Create `api/scenarios.py`:
  ```python
  from fastapi import APIRouter, Depends, HTTPException
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.schemas.scenario import ScenarioRequest, ScenarioResult
  from app.services import scenario_service
  from core.database import get_db

  router = APIRouter(prefix="/scenarios", tags=["scenarios"])


  @router.post("/run", response_model=ScenarioResult)
  async def run_scenario(
      request: ScenarioRequest,
      db: AsyncSession = Depends(get_db),
  ) -> ScenarioResult:
      try:
          return await scenario_service.run_scenario(db, request)
      except Exception as e:
          raise HTTPException(status_code=500, detail=f"Scenario simulation failed: {e}") from e
  ```
- [ ] Register in `core/app.py`:
  ```python
  from api.scenarios import router as scenarios_router
  app.include_router(scenarios_router, prefix="/api/v1")
  ```

---

### 4. Add MCP tool `run_scenario`

- [ ] Create `mcp_server/tools/scenarios.py`:
  ```python
  import json
  from decimal import Decimal

  from mcp.server import Server
  from mcp.types import TextContent

  from app.models.transaction import TransactionCategory
  from app.schemas.scenario import ScenarioRequest, SpendingChange
  from app.services import scenario_service
  from core.database import AsyncSessionLocal


  def register_scenario_tools(server: Server) -> None:
      @server.tool()
      async def run_scenario(
          category: str,
          reduction_pct: float,
          target_description: str,
          target_amount: float,
          extra_monthly_savings: float = 0.0,
      ) -> list[TextContent]:
          """Simulate what happens if you reduce spending in a category.

          Args:
              category: Spending category (e.g., food, transport, subscriptions)
              reduction_pct: Percentage to reduce (e.g., 50 for 50% cut)
              target_description: What you're saving for (e.g., MacBook Pro)
              target_amount: Target amount in rupees
              extra_monthly_savings: Additional fixed monthly savings on top of spending cuts
          """
          request = ScenarioRequest(
              spending_changes=[
                  SpendingChange(
                      category=TransactionCategory.coerce(category),
                      reduction_pct=reduction_pct,
                  )
              ],
              target_amount=Decimal(str(target_amount)),
              target_description=target_description,
              extra_monthly_savings=Decimal(str(extra_monthly_savings)),
          )
          async with AsyncSessionLocal() as db:
              result = await scenario_service.run_scenario(db, request)

          lines = [
              f"🎯 Goal: {target_description} (₹{target_amount:,.0f})",
              f"📉 Changes: {json.dumps(result.breakdown, indent=2)}",
              f"💰 Projected monthly savings: ₹{result.projected_monthly_savings:,.0f}",
              f"📅 Months to goal: {result.months_to_goal or 'Not achievable with current changes'}",
              f"\n{result.narrative}",
          ]
          return [TextContent(type="text", text="\n".join(lines))]
  ```
- [ ] Register in `mcp_server/server.py`:
  ```python
  from mcp_server.tools.scenarios import register_scenario_tools
  register_scenario_tools(server)
  ```

---

### 5. Write tests

- [ ] Create `tests/test_scenario_service.py`:
  ```python
  from decimal import Decimal
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest

  from app.models.transaction import TransactionCategory
  from app.schemas.scenario import ScenarioRequest, SpendingChange


  @pytest.mark.asyncio
  async def test_run_scenario_returns_result(db_session):
      mock_spending = [
          MagicMock(category=TransactionCategory.FOOD, total=Decimal("9000")),
      ]
      mock_claude_response = MagicMock()
      mock_claude_response.content = [MagicMock(text='{"months_to_goal": 6, "narrative": "You can do it!"}')]

      with (
          patch("app.services.scenario_service.get_spending_by_category", new_callable=AsyncMock, return_value=mock_spending),
          patch("app.services.scenario_service.client") as mock_client,
      ):
          mock_client.messages.create = AsyncMock(return_value=mock_claude_response)
          from app.services import scenario_service

          request = ScenarioRequest(
              spending_changes=[SpendingChange(category=TransactionCategory.FOOD, reduction_pct=50)],
              target_amount=Decimal("90000"),
              target_description="MacBook Pro",
          )
          result = await scenario_service.run_scenario(db_session, request)

      assert result.months_to_goal == 6
      assert result.projected_monthly_savings == Decimal("1500")  # 9000/3 * 50%
      assert "food" in result.breakdown
  ```
- [ ] Run tests:
  ```bash
  pytest tests/test_scenario_service.py -v
  ```

---

## Verification — Phase 05 Complete

- [ ] Start server and call `POST /api/v1/scenarios/run` via Swagger UI with a food category reduction — verify you get months_to_goal and a narrative
- [ ] `pytest tests/test_scenario_service.py -v` → all tests pass
- [ ] The demo story now works end-to-end: import CSV → run scenario → get answer
- [ ] `ruff check .` → no errors
- [ ] Commit:
  ```bash
  git add -A
  git commit -m "feat(scenarios): add what-if scenario engine with Claude-powered projections"
  ```

import json
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from anthropic import AsyncAnthropic, BadRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.scenario import ScenarioRequest, ScenarioResult
from app.services.transaction_service import get_spending_by_category
from core.config import settings

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def run_scenario(
    db: AsyncSession,
    session_id: uuid.UUID | None,
    request: ScenarioRequest,
) -> ScenarioResult:
    """Run a what-if financial scenario using real spending data and Claude projections.

    Computes the current monthly average spending baseline from the last 3 months.
    When session_id is None, aggregates spending across all sessions (total picture).
    When session_id is provided, scopes the baseline to that session only.

    Falls back to deterministic projection when Claude API is unavailable.

    Args:
        db: Async database session.
        session_id: UUID of the session to use for the baseline, or None for all sessions.
        request: Scenario parameters — spending changes, target amount and description.

    Returns:
        ScenarioResult with months to goal, projected savings, narrative, and breakdown.
    """
    today = date.today()
    three_months_ago = today - timedelta(days=90)
    spending = await get_spending_by_category(db, session_id, three_months_ago, today)

    # Monthly averages over the 3-month window
    monthly_avg: dict[str, Decimal] = {s.category.value: s.total / 3 for s in spending}

    breakdown: dict[str, str] = {}
    total_reduction = Decimal("0")

    for change in request.spending_changes:
        cat_key = change.category.value
        current = monthly_avg.get(cat_key, Decimal("0"))
        reduction = current * Decimal(str(change.reduction_pct / 100))
        new_amount = current - reduction
        breakdown[cat_key] = f"₹{current:,.0f}/month → ₹{new_amount:,.0f}/month"
        total_reduction += reduction

    projected_monthly_savings = total_reduction + request.extra_monthly_savings

    months_to_goal, narrative = await _project_with_claude(
        target_description=request.target_description,
        target_amount=request.target_amount,
        projected_monthly_savings=projected_monthly_savings,
        breakdown=breakdown,
        extra_monthly_savings=request.extra_monthly_savings,
    )

    return ScenarioResult(
        months_to_goal=months_to_goal,
        projected_monthly_savings=projected_monthly_savings,
        current_monthly_savings=Decimal("0"),
        narrative=narrative,
        breakdown=breakdown,
    )


async def _project_with_claude(
    target_description: str,
    target_amount: Decimal,
    projected_monthly_savings: Decimal,
    breakdown: dict[str, str],
    extra_monthly_savings: Decimal,
) -> tuple[int | None, str]:
    """Ask Claude to compute months to goal and write a motivating narrative.

    Falls back to deterministic calculation when Claude API is unavailable.

    Args:
        target_description: Human-readable goal name (e.g., "MacBook Pro").
        target_amount: Goal amount in rupees.
        projected_monthly_savings: Total monthly savings from spending cuts.
        breakdown: Per-category spend change summary strings.
        extra_monthly_savings: Additional fixed savings on top of cuts.

    Returns:
        Tuple of (months_to_goal or None, narrative string).
    """
    prompt_data = {
        "target": target_description,
        "target_amount": float(target_amount),
        "projected_monthly_savings": float(projected_monthly_savings),
        "spending_changes": breakdown,
        "extra_savings": float(extra_monthly_savings),
    }

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=(
                "You are a personal finance advisor. "
                "Given spending change data, calculate months to goal and write a motivating 2-sentence narrative. "
                "Respond ONLY with valid JSON: {\"months_to_goal\": int_or_null, \"narrative\": \"string\"}. "
                "If projected_monthly_savings <= 0, set months_to_goal to null."
            ),
            messages=[{"role": "user", "content": json.dumps(prompt_data)}],
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        return result.get("months_to_goal"), result.get("narrative", "")
    except (BadRequestError, Exception) as exc:
        logger.warning("Claude projection failed (%s), falling back to deterministic calculation.", exc)
        return _deterministic_projection(target_amount, projected_monthly_savings)


def _deterministic_projection(
    target_amount: Decimal,
    projected_monthly_savings: Decimal,
) -> tuple[int | None, str]:
    """Compute months to goal without Claude API.

    Args:
        target_amount: Goal amount in rupees.
        projected_monthly_savings: Projected savings per month.

    Returns:
        Tuple of (months_to_goal or None, plain-text narrative).
    """
    if projected_monthly_savings <= 0:
        return None, "The current spending changes don't free up enough savings to reach your goal. Try a larger reduction."

    months = int(target_amount / projected_monthly_savings) + 1
    narrative = (
        f"By making these spending changes you would save ₹{projected_monthly_savings:,.0f}/month. "
        f"At that rate you would reach your goal of ₹{target_amount:,.0f} in approximately {months} months."
    )
    return months, narrative

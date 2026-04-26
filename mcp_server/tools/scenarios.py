from decimal import Decimal

from mcp.server.fastmcp import FastMCP

from app.models.transaction import TransactionCategory
from app.schemas.scenario import ScenarioRequest, SpendingChange
from app.services import scenario_service, session_service
from core.config import settings
from core.database import AsyncSessionLocal


async def _resolve_session(session_name: str):
    name = session_name.strip() if session_name.strip() else settings.finsight_session
    async with AsyncSessionLocal() as db:
        session = await session_service.get_or_create_by_name(db, name)
        return session.id


def register_scenario_tools(mcp: FastMCP) -> None:

    @mcp.tool()
    async def run_scenario(
        category: str,
        reduction_pct: float,
        target_description: str,
        target_amount: float,
        extra_monthly_savings: float = 0.0,
        session_name: str = "",
    ) -> str:
        """Simulate what happens if you reduce spending in a category and project time to goal.

        Uses the last 3 months of real transaction data as the spending baseline.

        Examples:
            - "If I cut food by 50%, when can I afford a MacBook Pro (₹90,000)?"
              → category="food", reduction_pct=50, target_description="MacBook Pro", target_amount=90000
            - "If I save ₹5000 extra/month, when do I hit ₹1,00,000 emergency fund?"
              → category="other", reduction_pct=1, extra_monthly_savings=5000, target_amount=100000

        Args:
            category: Spending category to cut (food, transport, subscriptions, utilities,
                      entertainment, shopping, healthcare, other).
            reduction_pct: Percentage to reduce spending by (e.g., 50 for a 50% cut).
            target_description: What you're saving for (e.g., "MacBook Pro", "Goa trip").
            target_amount: Target amount in rupees.
            extra_monthly_savings: Additional fixed monthly savings on top of spending cuts.
            session_name: Which session to use (e.g., "hdfc credit card").
                          Leave empty to use the default session.
        """
        sid = await _resolve_session(session_name)

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
            result = await scenario_service.run_scenario(db, sid, request)

        label = f" [{session_name.strip()}]" if session_name.strip() else ""
        months_str = str(result.months_to_goal) if result.months_to_goal else "Not achievable with current changes"

        lines = [
            f"Goal{label}: {target_description} (₹{target_amount:,.0f})",
            f"Spending changes:",
        ]
        for cat, change in result.breakdown.items():
            lines.append(f"  {cat}: {change}")
        lines += [
            f"Projected monthly savings: ₹{result.projected_monthly_savings:,.0f}",
            f"Months to goal: {months_str}",
            f"",
            result.narrative,
        ]
        return "\n".join(lines)

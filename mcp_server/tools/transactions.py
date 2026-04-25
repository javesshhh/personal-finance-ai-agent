from datetime import date

from mcp.server import Server
from mcp.types import TextContent

from app.services import transaction_service
from core.database import AsyncSessionLocal


def register_transaction_tools(server: Server) -> None:
    @server.tool()
    async def get_spending(start_date: str, end_date: str) -> list[TextContent]:
        """Get spending totals by category between two dates.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
        """
        async with AsyncSessionLocal() as db:
            results = await transaction_service.get_spending_by_category(
                db,
                date.fromisoformat(start_date),
                date.fromisoformat(end_date),
            )
        if not results:
            return [TextContent(type="text", text="No spending data found for that date range.")]
        lines = [f"{r.category.value}: ₹{r.total:,.2f} ({r.count} transactions)" for r in results]
        return [TextContent(type="text", text="\n".join(lines))]

    @server.tool()
    async def compare_months(year_a: int, month_a: int, year_b: int, month_b: int) -> list[TextContent]:
        """Compare spending by category between two calendar months.

        Args:
            year_a: Year of the first month (e.g. 2024).
            month_a: Month number of the first month (1-12).
            year_b: Year of the second month.
            month_b: Month number of the second month (1-12).
        """
        async with AsyncSessionLocal() as db:
            results = await transaction_service.compare_months(db, year_a, month_a, year_b, month_b)
        if not results:
            return [TextContent(type="text", text="No data found for the requested months.")]
        lines = [
            f"{r.category.value}: ₹{r.month_a_total:,.2f} → ₹{r.month_b_total:,.2f} "
            f"({'↑' if r.delta > 0 else '↓'} {abs(r.delta_pct):.1f}%)"
            for r in results
        ]
        return [TextContent(type="text", text="\n".join(lines))]

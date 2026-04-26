from mcp.server.fastmcp import FastMCP

from app.services import session_service, subscription_service
from core.config import settings
from core.database import AsyncSessionLocal


async def _resolve_session(session_name: str):
    name = session_name.strip() if session_name.strip() else settings.finsight_session
    async with AsyncSessionLocal() as db:
        session = await session_service.get_or_create_by_name(db, name)
        return session.id


def register_subscription_tools(mcp: FastMCP) -> None:

    @mcp.tool()
    async def audit_subscriptions(session_name: str = "") -> str:
        """List all detected recurring subscriptions with waste scores.

        Run this after importing transactions to see which subscriptions
        were found and how wasteful they are rated (0 = essential, 100 = wasteful).

        Args:
            session_name: Which session to audit (e.g. "hdfc credit card").
                          Leave empty to use the default session.
        """
        sid = await _resolve_session(session_name)
        async with AsyncSessionLocal() as db:
            subs = await subscription_service.get_all_subscriptions(db, sid)

        label = f" [{session_name.strip()}]" if session_name.strip() else ""
        if not subs:
            return f"No subscriptions detected{label} yet. Try asking me to detect subscriptions first."

        lines = [
            f"{s.name}: ₹{s.latest_amount} every ~{s.frequency_days} days | "
            f"Waste score: {s.waste_score if s.waste_score is not None else 'N/A'}/100"
            + (f" — {s.waste_reason}" if s.waste_reason else "")
            for s in subs
        ]
        return f"Subscriptions{label}:\n" + "\n".join(lines)

    @mcp.tool()
    async def detect_subscriptions(session_name: str = "") -> str:
        """Scan transactions and detect recurring subscriptions for a session.

        Call this after importing new statements to refresh subscription data.

        Args:
            session_name: Which session to scan (e.g. "hdfc credit card").
                          Leave empty to use the default session.
        """
        sid = await _resolve_session(session_name)
        async with AsyncSessionLocal() as db:
            subs = await subscription_service.detect_subscriptions(db, sid)

        label = f" [{session_name.strip()}]" if session_name.strip() else ""
        if not subs:
            return f"No recurring subscriptions found{label}. Make sure subscription transactions are imported."

        lines = [f"- {s.name}: ₹{s.latest_amount} every ~{s.frequency_days} days" for s in subs]
        return f"Detected {len(subs)} subscription(s){label}:\n" + "\n".join(lines)

    @mcp.tool()
    async def flag_price_changes(session_name: str = "") -> str:
        """Show subscriptions that have increased in price since last detection.

        Args:
            session_name: Which session to check (e.g. "hdfc credit card").
                          Leave empty to use the default session.
        """
        sid = await _resolve_session(session_name)
        async with AsyncSessionLocal() as db:
            alerts = await subscription_service.get_price_changes(db, sid)

        label = f" [{session_name.strip()}]" if session_name.strip() else ""
        if not alerts:
            return f"No price increases detected{label}."

        lines = [
            f"⚠ {a.name}: ₹{a.previous_amount} → ₹{a.latest_amount} (+{a.change_pct}%)"
            for a in alerts
        ]
        return f"Price increases{label}:\n" + "\n".join(lines)

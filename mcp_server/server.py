import asyncio
import uuid

from mcp.server.fastmcp import FastMCP

from app.services import session_service
from core.config import settings
from core.database import AsyncSessionLocal
from mcp_server.tools.transactions import register_transaction_tools

mcp = FastMCP("finsight")

# Resolved once at startup — all tools use this session_id
_session_id: uuid.UUID | None = None


async def _resolve_session() -> uuid.UUID:
    """Look up or create the session named in FINSIGHT_SESSION env var."""
    async with AsyncSessionLocal() as db:
        session = await session_service.get_or_create_by_name(db, settings.finsight_session)
        return session.id


def get_session_id() -> uuid.UUID:
    """Return the active session ID resolved at startup."""
    if _session_id is None:
        raise RuntimeError("MCP server session not initialized")
    return _session_id


register_transaction_tools(mcp, get_session_id)

# Tools registered as each phase completes:
# from mcp_server.tools.subscriptions import register_subscription_tools
# from mcp_server.tools.scenarios import register_scenario_tools
# from mcp_server.tools.health_score import register_health_score_tools
# from mcp_server.tools.goals import register_goal_tools

if __name__ == "__main__":
    _session_id = asyncio.run(_resolve_session())
    mcp.run(transport="stdio")

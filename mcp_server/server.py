import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server

from mcp_server.tools.transactions import register_transaction_tools

server = Server("finsight")

register_transaction_tools(server)

# Tools registered as each phase completes:
# from mcp_server.tools.subscriptions import register_subscription_tools
# from mcp_server.tools.scenarios import register_scenario_tools
# from mcp_server.tools.health_score import register_health_score_tools
# from mcp_server.tools.goals import register_goal_tools


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

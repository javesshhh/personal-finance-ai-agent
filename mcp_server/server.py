from mcp.server.fastmcp import FastMCP

from mcp_server.tools.scenarios import register_scenario_tools
from mcp_server.tools.subscriptions import register_subscription_tools
from mcp_server.tools.transactions import register_transaction_tools

mcp = FastMCP("finsight")

register_transaction_tools(mcp)
register_subscription_tools(mcp)
register_scenario_tools(mcp)

# Tools registered as each phase completes:
# from mcp_server.tools.health_score import register_health_score_tools
# from mcp_server.tools.goals import register_goal_tools

mcp.run(transport="stdio")

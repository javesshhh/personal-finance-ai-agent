# Phase 08 — MCP Server Wiring & Claude Desktop Integration

## Overview

By Phase 07, all MCP tools exist in separate files. This phase:
1. Verifies all 8 tools are properly registered
2. Creates the MCP server startup script
3. Configures Claude Desktop to use the server
4. Runs an end-to-end smoke test: query Claude Desktop → MCP tool → DB → real answer

This is the phase where the project becomes a real MCP-powered AI assistant.

---

## Pros / Cons of Key Decisions

### Decision: stdio transport vs. HTTP/SSE transport

| | stdio | HTTP/SSE |
|---|---|---|
| **Pro** | Native Claude Desktop support; no network config | Works over network; multi-client |
| **Con** | Only one client at a time | More complex setup; Claude Desktop requires specific config |
| **Verdict** | ✅ stdio — Claude Desktop uses stdio by default and it's the simplest path |

### Decision: Run MCP server as a separate process vs. embedded in FastAPI

| | Separate process | Embedded |
|---|---|---|
| **Pro** | Clean separation; can restart independently; Claude Desktop expects a standalone script | One process to manage |
| **Con** | Must ensure DB/env available when MCP process starts | Couples MCP and API lifecycle |
| **Verdict** | ✅ Separate process — this is how MCP is designed and what Claude Desktop expects |

### Decision: Single `server.py` registering all tools vs. per-feature server files

| | Single server.py | Per-feature server files |
|---|---|---|
| **Pro** | One entry point, easy to find | Isolated; easier to test |
| **Con** | Gets long as tools grow | Multiple entry points to manage |
| **Verdict** | ✅ Single server.py with modular `register_*_tools()` functions — already the pattern from previous phases |

---

## Checklist

### 1. Finalize `mcp_server/server.py` with all tools registered

- [ ] Ensure `mcp_server/server.py` looks like this (all tools registered):
  ```python
  import asyncio

  from mcp.server import Server
  from mcp.server.stdio import stdio_server

  from mcp_server.tools.transactions import register_transaction_tools
  from mcp_server.tools.subscriptions import register_subscription_tools
  from mcp_server.tools.scenarios import register_scenario_tools
  from mcp_server.tools.health_score import register_health_score_tools
  from mcp_server.tools.goals import register_goal_tools

  server = Server("finsight")

  register_transaction_tools(server)
  register_subscription_tools(server)
  register_scenario_tools(server)
  register_health_score_tools(server)
  register_goal_tools(server)


  async def main() -> None:
      async with stdio_server() as (read_stream, write_stream):
          await server.run(read_stream, write_stream, server.create_initialization_options())


  if __name__ == "__main__":
      asyncio.run(main())
  ```
- [ ] Verify all tool files exist:
  ```bash
  ls mcp_server/tools/
  # Expected: __init__.py  transactions.py  subscriptions.py  scenarios.py  health_score.py  goals.py
  ```

---

### 2. Verify the MCP server starts and lists tools

- [ ] Start the MCP server manually to confirm no import errors:
  ```bash
  python -m mcp_server.server
  # Should block (waiting for stdio input) — Ctrl+C to exit
  ```
- [ ] Use the MCP inspector to verify all tools are listed (requires `npx`):
  ```bash
  npx @modelcontextprotocol/inspector python -m mcp_server.server
  # Opens browser at http://localhost:5173 — verify all 8 tools appear
  ```
  Expected tools list:
  - `get_spending`
  - `compare_months`
  - `audit_subscriptions`
  - `flag_price_changes`
  - `run_scenario`
  - `get_health_score`
  - `set_goal`
  - `get_goals`

---

### 3. Configure Claude Desktop

- [ ] Find the Claude Desktop config file:
  - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
  - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- [ ] Open/create the config and add the finsight server:
  ```json
  {
    "mcpServers": {
      "finsight": {
        "command": "/absolute/path/to/.venv/bin/python",
        "args": ["-m", "mcp_server.server"],
        "cwd": "/absolute/path/to/personal-finance-ai-agent",
        "env": {
          "DATABASE_URL": "postgresql+asyncpg://finsight:finsight@localhost:5432/finsight",
          "REDIS_URL": "redis://localhost:6379",
          "ANTHROPIC_API_KEY": "your_key_here"
        }
      }
    }
  }
  ```
- [ ] Replace `/absolute/path/to/` with your actual path. Get it with:
  ```bash
  echo $(pwd)            # project root
  echo $(which python)   # .venv python path
  ```
- [ ] Quit and relaunch Claude Desktop completely (Cmd+Q, not just close window)
- [ ] Verify the server connected: look for the 🔌 MCP icon in Claude Desktop's input area

---

### 4. Run end-to-end smoke tests from Claude Desktop

Before running these, ensure:
- Docker containers are running (`docker compose up -d`)
- FastAPI server is NOT required — MCP server talks directly to DB
- You have at least 2 months of transaction data imported

- [ ] **Test `get_spending`**: Ask Claude:
  > "What did I spend on food in January 2024?"
  Expected: Claude calls `get_spending` and returns a formatted breakdown

- [ ] **Test `compare_months`**: Ask Claude:
  > "Compare my January vs February 2024 spending"
  Expected: Claude calls `compare_months` and returns category deltas

- [ ] **Test `audit_subscriptions`**: Ask Claude:
  > "What subscriptions am I paying for and which ones am I wasting money on?"
  Expected: Claude calls `audit_subscriptions` and lists subscriptions with waste scores

- [ ] **Test `run_scenario`**: Ask Claude:
  > "If I cut my food delivery spending by 50%, how long would it take me to save ₹90,000 for a MacBook Pro?"
  Expected: Claude calls `run_scenario` and returns months + narrative

- [ ] **Test `get_health_score`**: Ask Claude:
  > "What's my financial health score this week?"
  Expected: Claude calls `get_health_score` and returns the score breakdown

- [ ] **Test `set_goal`**: Ask Claude:
  > "Set a goal for me: save ₹50,000 for an emergency fund by December 2024"
  Expected: Claude calls `set_goal` and confirms the goal was created

- [ ] **Test `get_goals`**: Ask Claude:
  > "Show me all my savings goals and how I'm progressing"
  Expected: Claude calls `get_goals` with progress percentages

- [ ] **Test `flag_price_changes`**: Ask Claude:
  > "Have any of my subscriptions increased in price?"
  Expected: Claude calls `flag_price_changes` and lists any increases

---

### 5. Handle common MCP errors

| Error | Likely cause | Fix |
|---|---|---|
| Server not appearing in Claude Desktop | Config JSON syntax error | Validate JSON at jsonlint.com |
| "Tool not found" | Tool not registered in server.py | Check register_*_tools() calls |
| DB connection error | Docker not running | `docker compose up -d` |
| Import error on startup | Missing `__init__.py` or wrong venv path | Check `which python` matches config `command` |
| `asyncpg` event loop error | asyncio loop conflict in MCP context | Use `asyncio.run()` in each tool call; don't share loops |

---

### 6. Add a convenience startup script

- [ ] Create `scripts/start_mcp.sh`:
  ```bash
  #!/bin/bash
  set -e
  cd "$(dirname "$0")/.."
  source .venv/bin/activate
  export $(cat .env | xargs)
  exec python -m mcp_server.server
  ```
- [ ] Make it executable:
  ```bash
  chmod +x scripts/start_mcp.sh
  mkdir -p scripts
  ```
- [ ] Update `claude_desktop_config.json` to use the script instead:
  ```json
  {
    "mcpServers": {
      "finsight": {
        "command": "/absolute/path/to/personal-finance-ai-agent/scripts/start_mcp.sh"
      }
    }
  }
  ```

---

## Verification — Phase 08 Complete

- [ ] `npx @modelcontextprotocol/inspector python -m mcp_server.server` → all 8 tools listed
- [ ] All 8 Claude Desktop smoke tests pass
- [ ] Claude Desktop shows finsight in the 🔌 MCP servers list
- [ ] `ruff check .` → no errors
- [ ] Commit:
  ```bash
  git add -A
  git commit -m "feat(mcp): wire all MCP tools, add Claude Desktop config and startup script"
  ```

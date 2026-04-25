# FinSight — Personal Finance Intelligence Agent

> Upload 3 months of bank statements → Ask what you're wasting money on → AI flags forgotten subscriptions and shows you could afford a Goa trip in 6 months by cutting food delivery in half.

---

## What is this?

FinSight is a personal finance AI agent built on **FastAPI + PostgreSQL + Claude AI + MCP**. It turns raw bank CSV exports into actionable financial intelligence — surfacing subscription waste, running "what-if" scenarios, and generating a weekly health score — all queryable from Claude Desktop via the Model Context Protocol.

---

## Features

| Feature | Description |
|---|---|
| **CSV Import + AI Categorisation** | Upload any bank export → Claude auto-categorises every transaction into food, transport, subscriptions, etc. |
| **What-If Scenario Engine** | *"If I cut food delivery by 50%, when can I afford a MacBook Pro?"* — Claude runs the projection using your real spending data |
| **Subscription Intelligence** | Auto-detects recurring charges, tracks price increases, scores each subscription by waste level |
| **Financial Health Score** | Weekly 0–100 score across savings rate, budget adherence, subscription waste, and unusual spends |
| **Budget & Goal Tracking** | Set monthly budgets per category, create savings goals with deadlines, track progress |
| **MCP Tools** | All features queryable from Claude Desktop via natural language |

---

## Architecture

```
You
 │
 ▼
Claude Desktop ──────────────────────────────────────────┐
 │                                                        │
 │  natural language                               MCP tools
 ▼                                                        │
[MCP Server]  ◄──────────────────────────────────────────┘
 │
 ├── get_spending          ──┐
 ├── compare_months          │
 ├── audit_subscriptions     │──► FastAPI Backend ──► PostgreSQL
 ├── flag_price_changes      │         │
 ├── run_scenario            │         ▼
 ├── get_health_score     ──┘    Claude API (claude-sonnet-4-6)
 ├── set_goal                    - categorisation
 └── get_goals                   - scenario simulation
                                 - weekly digest generation
                                          │
                                          ▼
                                   Redis + Celery
                                  (weekly health score job)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI 0.100+ with async/await |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 15 |
| Cache / Broker | Redis 7 |
| Background Jobs | Celery |
| AI | Anthropic Claude (`claude-sonnet-4-6`) |
| MCP | `mcp` Python SDK |
| Migrations | Alembic |
| Python | 3.11 |
| Linting | Ruff |

---

## Local Setup

### Prerequisites

- Python 3.11
- Docker Desktop
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Clone and create virtual environment

```bash
git clone git@github.com:javesshhh/personal-finance-ai-agent.git
cd personal-finance-ai-agent

python3.11 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements_dev.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your `ANTHROPIC_API_KEY`:

```env
DATABASE_URL=postgresql+asyncpg://finsight:finsight@localhost:5433/finsight
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=sk-ant-...
MCP_SERVER_PORT=8001
API_PORT=8000
ENVIRONMENT=development
```

### 4. Start Postgres + Redis

```bash
docker compose up -d
```

> **Note:** Postgres runs on port `5433` (not `5432`) to avoid conflicts with other local Postgres instances.

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Start the API server

```bash
python main.py
```

API is live at **http://localhost:8000**
Swagger UI at **http://localhost:8000/docs**

---

## Running the Services

You'll typically need 3–4 terminals:

```bash
# Terminal 1 — Postgres + Redis
docker compose up -d

# Terminal 2 — FastAPI server
source .venv/bin/activate && python main.py

# Terminal 3 — Celery worker (background jobs)
source .venv/bin/activate
celery -A core.celery_app.celery_app worker --loglevel=info

# Terminal 4 — MCP server (for Claude Desktop)
source .venv/bin/activate
python -m mcp_server.server
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check with DB connectivity |
| `POST` | `/api/v1/transactions/` | Create a transaction manually |
| `POST` | `/api/v1/transactions/import-csv` | Bulk import from bank CSV |
| `GET` | `/api/v1/transactions/spending` | Spending by category for a date range |
| `GET` | `/api/v1/transactions/compare` | Month-over-month spending comparison |
| `POST` | `/api/v1/subscriptions/detect` | Detect recurring charges from transactions |
| `GET` | `/api/v1/subscriptions/` | List subscriptions with waste scores |
| `GET` | `/api/v1/subscriptions/price-changes` | Subscriptions with price increases |
| `POST` | `/api/v1/scenarios/run` | Run a what-if financial scenario |
| `POST` | `/api/v1/health-score/generate` | Generate this week's health score |
| `GET` | `/api/v1/health-score/` | Get latest health score with digest |
| `POST` | `/api/v1/budgets/` | Create or update a category budget |
| `GET` | `/api/v1/budgets/` | List budgets for a month |
| `POST` | `/api/v1/goals/` | Create a savings goal |
| `GET` | `/api/v1/goals/` | List goals with progress |

Full interactive docs: `http://localhost:8000/docs`

---

## MCP Tools (Claude Desktop)

Connect Claude Desktop to FinSight by adding this to your `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "finsight": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/personal-finance-ai-agent",
      "env": {
        "DATABASE_URL": "postgresql+asyncpg://finsight:finsight@localhost:5433/finsight",
        "REDIS_URL": "redis://localhost:6379",
        "ANTHROPIC_API_KEY": "your_key_here"
      }
    }
  }
}
```

Once connected, ask Claude things like:

- *"What did I spend the most on last month?"*
- *"What subscriptions am I wasting money on?"*
- *"If I cut food delivery by 50%, when can I save ₹90,000 for a MacBook Pro?"*
- *"What's my financial health score this week?"*
- *"Set a goal: save ₹1,00,000 for an emergency fund by December 2024"*

---

## CSV Import Format

Your bank export CSV must have these columns (case-insensitive):

```csv
date,description,amount
2024-01-15,Swiggy order,-450.00
2024-01-16,Uber ride,-230.00
2024-01-17,Salary credit,85000.00
```

- **date**: `YYYY-MM-DD`
- **description**: transaction description from your bank
- **amount**: negative for debits, positive for credits

---

## Project Structure

```
├── api/                  # FastAPI route handlers (thin — validate + route only)
├── app/
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   └── services/         # Business logic (categoriser, scenario engine, etc.)
├── mcp_server/
│   ├── server.py         # MCP server entry point
│   └── tools/            # One file per feature group
├── core/                 # Config, DB engine, app factory, Celery
├── celery_tasks/         # Background job definitions
├── migrations/           # Alembic migration files
├── tests/                # pytest test suite
├── docs/
│   ├── phases/           # Step-by-step build guide (10 phases)
│   └── architecture-decisions.md  # Why every major choice was made
├── docker-compose.yml    # Postgres + Redis
├── BUILD_PLAN.md         # Master progress tracker
└── CLAUDE.md             # AI session context
```

---

## Build Progress

| Phase | Status |
|---|---|
| 01 — Environment Setup | ✅ Done |
| 02 — Core Infrastructure | ✅ Done |
| 03 — Transaction Management | ✅ Done |
| 04 — Subscription Intelligence | ⬜ |
| 05 — Scenario Engine | ⬜ |
| 06 — Health Score | ⬜ |
| 07 — Budgets & Goals | ⬜ |
| 08 — MCP Server | ⬜ |
| 09 — Testing & CI | ⬜ |
| 10 — Deployment | ⬜ |

---

## Cost

| Item | Monthly estimate |
|---|---|
| Anthropic API (personal use) | < $0.20 |
| Railway hosting (demo deploy) | $0–$5 |
| **Total** | **~$0 during dev; $0–$5 deployed** |

---

## Contributing

This is a personal project. Architecture decisions and reasoning are documented in [`docs/architecture-decisions.md`](docs/architecture-decisions.md).

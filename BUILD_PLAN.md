# FinSight — Build Plan

Personal implementation roadmap. Tick off as you go.

---

## Progress Overview

| Phase | Title | Status | Est. Days |
|-------|-------|--------|-----------|
| [01](docs/phases/01-environment-setup.md) | Environment & Project Setup | ✅ Done | 0.5 |
| [02](docs/phases/02-core-infrastructure.md) | Core Infrastructure | ✅ Done | 1 |
| [03](docs/phases/03-transactions.md) | Transaction Management | ✅ Done | 2 |
| [04](docs/phases/04-subscriptions.md) | Subscription Intelligence | ⬜ Not started | 1.5 |
| [05](docs/phases/05-scenario-engine.md) | What-If Scenario Engine | ⬜ Not started | 1 |
| [06](docs/phases/06-health-score.md) | Financial Health Score | ⬜ Not started | 1.5 |
| [07](docs/phases/07-budgets-and-goals.md) | Budget & Goal Tracking | ⬜ Not started | 1.5 |
| [08](docs/phases/08-mcp-server.md) | MCP Server Wiring | ⬜ Not started | 1 |
| [09](docs/phases/09-testing-and-quality.md) | Testing & Code Quality | ⬜ Not started | 1 |
| [10](docs/phases/10-deployment.md) | Deployment | ⬜ Not started | 1 |
| [11](docs/phases/11-multi-user.md) | Multi-User Support | ⬜ Not started | 2 |

**Update the status column as you work:**
- `⬜ Not started`
- `🔄 In progress`
- `✅ Done`

**Total estimated build time: ~14 days** (solo developer, part-time evenings)

---

## Quick Reference

### Start the local stack
```bash
# Terminal 1 — Postgres + Redis
docker compose up -d

# Terminal 2 — FastAPI server
source .venv/bin/activate
python main.py

# Terminal 3 — Celery worker (needed for background jobs)
celery -A core.celery_app.celery_app worker --loglevel=info

# Terminal 4 — MCP server (for Claude Desktop)
python -m mcp_server.server
```

### Run tests
```bash
pytest tests/ -v --cov=app --cov-fail-under=80
```

### Lint
```bash
ruff check .
```

### Create a migration
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Deploy to Railway
```bash
railway up
```

---

## API Endpoints Summary

Once fully built, the API exposes:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/transactions/` | Create transaction |
| POST | `/api/v1/transactions/import-csv` | Bulk import from CSV |
| GET | `/api/v1/transactions/spending` | Spending by category |
| GET | `/api/v1/transactions/compare` | Compare two months |
| POST | `/api/v1/subscriptions/detect` | Detect subscriptions from transactions |
| GET | `/api/v1/subscriptions/` | List subscriptions with waste scores |
| GET | `/api/v1/subscriptions/price-changes` | Subscriptions with price increases |
| POST | `/api/v1/scenarios/run` | Run a what-if scenario |
| POST | `/api/v1/health-score/generate` | Generate this week's health score |
| GET | `/api/v1/health-score/` | Get latest health score |
| POST | `/api/v1/budgets/` | Create/update a budget |
| GET | `/api/v1/budgets/` | List budgets for a month |
| POST | `/api/v1/goals/` | Create a savings goal |
| GET | `/api/v1/goals/` | List goals with progress |

Swagger UI: `http://localhost:8000/docs`

---

## MCP Tools Summary

| Tool | Phase | Description |
|------|-------|-------------|
| `get_spending` | 03 | Spending by category for a date range |
| `compare_months` | 03 | Month-over-month spending comparison |
| `audit_subscriptions` | 04 | List subscriptions with waste scores |
| `flag_price_changes` | 04 | Detect subscription price increases |
| `run_scenario` | 05 | What-if projection |
| `get_health_score` | 06 | Weekly financial health score |
| `set_goal` | 07 | Create a savings goal |
| `get_goals` | 07 | List goals with progress |

---

## Directory Structure (final)

```
personal-finance-ai-agent/
├── api/                        # FastAPI route handlers (thin layer — validate + route only)
│   ├── health.py
│   ├── transactions.py
│   ├── subscriptions.py
│   ├── scenarios.py
│   ├── health_score.py
│   ├── budgets.py
│   └── goals.py
├── app/
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── __init__.py         # Import all models here (Alembic needs this)
│   │   ├── transaction.py
│   │   ├── subscription.py
│   │   ├── health_score.py
│   │   ├── budget.py
│   │   └── goal.py
│   ├── schemas/                # Pydantic request/response schemas
│   │   ├── transaction.py
│   │   ├── subscription.py
│   │   ├── scenario.py
│   │   ├── health_score.py
│   │   ├── budget.py
│   │   └── goal.py
│   └── services/               # Business logic — all orchestration lives here
│       ├── transaction_service.py
│       ├── categorizer.py
│       ├── subscription_service.py
│       ├── scenario_service.py
│       ├── health_score_service.py
│       ├── budget_service.py
│       └── goal_service.py
├── mcp_server/
│   ├── server.py               # MCP server entry point
│   └── tools/
│       ├── transactions.py
│       ├── subscriptions.py
│       ├── scenarios.py
│       ├── health_score.py
│       └── goals.py
├── core/
│   ├── config.py               # Settings (pydantic-settings, reads .env)
│   ├── database.py             # Engine, session factory, Base, get_db()
│   ├── app.py                  # FastAPI app factory + router registration
│   └── celery_app.py           # Celery app + beat schedule
├── celery_tasks/
│   └── health_score.py         # Weekly health score Celery task
├── migrations/                 # Alembic migration files (auto-generated)
├── tests/
│   ├── conftest.py             # pytest fixtures (engine, db_session, client)
│   ├── test_transaction_service.py
│   ├── test_subscription_service.py
│   ├── test_scenario_service.py
│   ├── test_health_score_service.py
│   ├── test_budget_service.py
│   ├── test_api_transactions.py
│   └── test_api_budgets.py
├── docs/
│   ├── phases/                 # Phase-by-phase build guide (this repo)
│   └── architecture-decisions.md
├── scripts/
│   └── start_mcp.sh
├── .github/workflows/ci.yml    # GitHub Actions CI
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml              # Ruff config + pytest config
├── requirements.in             # Direct dependencies
├── requirements.txt            # Pinned (generated by pip-compile)
├── requirements_dev.in
├── requirements_dev.txt
├── .env                        # Local secrets (gitignored)
├── .env.example                # Template (committed)
├── .gitignore
├── BUILD_PLAN.md               # This file
├── CLAUDE.md                   # Project context for Claude Code sessions
└── main.py                     # Uvicorn entrypoint
```

---

## Cost Summary

| Item | Monthly cost |
|------|-------------|
| Anthropic API (personal use) | < $0.20 |
| Railway hosting (free tier credit) | $0–$5 |
| Everything else | $0 |
| **Total** | **$0–$5/month** |

---

## Key Docs

- [Architecture Decisions](docs/architecture-decisions.md) — why every major technical choice was made
- [Phase 01: Setup](docs/phases/01-environment-setup.md)
- [Phase 02: Infrastructure](docs/phases/02-core-infrastructure.md)
- [Phase 03: Transactions](docs/phases/03-transactions.md)
- [Phase 04: Subscriptions](docs/phases/04-subscriptions.md)
- [Phase 05: Scenarios](docs/phases/05-scenario-engine.md)
- [Phase 06: Health Score](docs/phases/06-health-score.md)
- [Phase 07: Budgets & Goals](docs/phases/07-budgets-and-goals.md)
- [Phase 08: MCP Server](docs/phases/08-mcp-server.md)
- [Phase 09: Testing & CI](docs/phases/09-testing-and-quality.md)
- [Phase 10: Deployment](docs/phases/10-deployment.md)
- [Phase 11: Multi-User Support](docs/phases/11-multi-user.md)

# FinSight — Build Plan

Personal implementation roadmap. Tick off as you go.

---

## Progress Overview

| Phase | Title | Status | Est. Days |
|-------|-------|--------|-----------|
| [01](docs/phases/01-environment-setup.md) | Environment & Project Setup | ✅ Done | 0.5 |
| [02](docs/phases/02-core-infrastructure.md) | Core Infrastructure | ✅ Done | 1 |
| [03](docs/phases/03-transactions.md) | Transaction Management + Sessions + PDF | ✅ Done | 3 |
| [04](docs/phases/04-subscriptions.md) | Subscription Intelligence | ✅ Done | 1.5 |
| [05](docs/phases/05-scenario-engine.md) | What-If Scenario Engine | ✅ Done | 1 |
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
uvicorn "core.app:create_app" --factory --port 8000

# Terminal 3 — Celery worker (needed for background jobs)
celery -A core.celery_app.celery_app worker --loglevel=info
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

Live endpoints (phases 01–05 complete):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/sessions/` | Create a named session (e.g. "hdfc credit card") |
| GET | `/api/v1/sessions/` | List all sessions |
| DELETE | `/api/v1/sessions/{id}` | Delete a session and all its data |
| POST | `/api/v1/transactions/?session_id=` | Create single transaction |
| POST | `/api/v1/transactions/import-csv?session_id=` | Bulk import from CSV into session |
| POST | `/api/v1/transactions/import-pdf?session_id=` | Bulk import from PDF into session |
| GET | `/api/v1/transactions/spending?session_id=` | Spending by category |
| GET | `/api/v1/transactions/compare?session_id=` | Compare two months |
| POST | `/api/v1/subscriptions/detect?session_id=` | Detect subscriptions from transactions |
| GET | `/api/v1/subscriptions/?session_id=` | List subscriptions with waste scores |
| GET | `/api/v1/subscriptions/price-changes?session_id=` | Subscriptions with price increases |
| POST | `/api/v1/scenarios/run?session_id=` | Run a what-if scenario |

Planned endpoints (future phases):

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/health-score/generate` | Generate this week's health score |
| GET | `/api/v1/health-score/` | Get latest health score |
| POST | `/api/v1/budgets/` | Create/update a budget |
| GET | `/api/v1/budgets/` | List budgets for a month |
| POST | `/api/v1/goals/` | Create a savings goal |
| GET | `/api/v1/goals/` | List goals with progress |

Swagger UI: `http://localhost:8000/docs`

---

## MCP Tools Summary

| Tool | Phase | Status | Description |
|------|-------|--------|-------------|
| `list_sessions` | 03 | ✅ Live | List all named sessions / accounts |
| `import_file` | 03 | ✅ Live | Import CSV or PDF into a named session |
| `get_spending` | 03 | ✅ Live | Spending by category for a date range; optional session_name |
| `compare_months` | 03 | ✅ Live | Month-over-month comparison; optional session_name |
| `audit_subscriptions` | 04 | ✅ Live | List subscriptions with waste scores |
| `detect_subscriptions` | 04 | ✅ Live | Scan and detect recurring subscriptions |
| `flag_price_changes` | 04 | ✅ Live | Detect subscription price increases |
| `run_scenario` | 05 | ✅ Live | What-if projection (reduce spending → months to goal) |
| `get_health_score` | 06 | ⬜ | Weekly financial health score |
| `set_goal` | 07 | ⬜ | Create a savings goal |
| `get_goals` | 07 | ⬜ | List goals with progress |

**Session behaviour:** all tools accept an optional `session_name` parameter. If omitted, they query the session named in `FINSIGHT_SESSION` env var (default: `"default"`). Querying from Claude Desktop — just mention the account name naturally and Claude passes it through.

---

## Directory Structure (current)

```
personal-finance-ai-agent/
├── api/
│   ├── health.py
│   ├── scenarios.py             # POST /scenarios/run
│   ├── sessions.py              # Session CRUD
│   ├── subscriptions.py         # detect, list, price-changes
│   └── transactions.py          # CSV + PDF import, spending, compare
├── app/
│   ├── models/
│   │   ├── session.py           # Session ORM (has cascade relationships)
│   │   ├── subscription.py      # Subscription ORM (session_id FK)
│   │   └── transaction.py       # Transaction ORM (session_id FK)
│   ├── schemas/
│   │   ├── scenario.py          # ScenarioRequest, ScenarioResult, SpendingChange
│   │   ├── session.py
│   │   ├── subscription.py      # SubscriptionRead, PriceChangeAlert
│   │   └── transaction.py
│   └── services/
│       ├── categorizer.py       # Claude API + keyword fallback
│       ├── pdf_parser.py        # pdfplumber + Claude API + regex fallback
│       ├── scenario_service.py  # run_scenario + _deterministic_projection fallback
│       ├── session_service.py   # create, list, get_or_create_by_name (fuzzy), delete
│       ├── subscription_service.py  # detect, score waste, list, price changes
│       └── transaction_service.py   # import, spending, compare, cross-session dedup
│   └── utils/
│       └── cross_session.py     # inter-session transfer detection (avoids double-counting)
├── mcp_server/
│   ├── server.py
│   └── tools/
│       ├── scenarios.py         # run_scenario MCP tool
│       ├── subscriptions.py     # audit_subscriptions, detect_subscriptions, flag_price_changes
│       └── transactions.py      # list_sessions, import_file, delete_session, get_spending, compare_months
├── core/
│   ├── config.py                # includes FINSIGHT_SESSION setting
│   ├── database.py              # echo=False (protects MCP stdio)
│   ├── app.py
│   └── celery_app.py
├── celery_tasks/
│   └── health_score.py
├── migrations/versions/         # 5 migrations applied
├── scripts/
│   ├── generate_dummy_pdfs.py   # hdfc_january/february_2025.pdf
│   └── generate_icici_pdf.py    # icici_march_2025.pdf
├── sample_transactions.csv
├── hdfc_january_2025.pdf
├── hdfc_february_2025.pdf
├── icici_march_2025.pdf
├── docker-compose.yml
├── requirements.in
├── .env
└── BUILD_PLAN.md
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

- [Architecture Decisions](docs/architecture-decisions.md)
- [Phase 03: Transactions + Sessions + PDF](docs/phases/03-transactions.md)
- [Phase 04: Subscriptions](docs/phases/04-subscriptions.md)
- [Phase 05: Scenarios](docs/phases/05-scenario-engine.md)
- [Phase 06: Health Score](docs/phases/06-health-score.md)
- [Phase 07: Budgets & Goals](docs/phases/07-budgets-and-goals.md)
- [Phase 08: MCP Server](docs/phases/08-mcp-server.md)
- [Phase 09: Testing & CI](docs/phases/09-testing-and-quality.md)
- [Phase 10: Deployment](docs/phases/10-deployment.md)
- [Phase 11: Multi-User Support](docs/phases/11-multi-user.md)

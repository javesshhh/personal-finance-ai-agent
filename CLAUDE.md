# FinSight — Personal Finance Intelligence Agent

## Project Overview

FinSight is a **Personal Finance Intelligence Agent** that combines a FastAPI backend, a custom MCP server, and Claude AI to give users proactive, conversational insights into their finances.

- **Language**: Python 3.11
- **Framework**: FastAPI with async SQLAlchemy, Celery, Redis
- **AI**: Claude API (categorization, scenario simulation, weekly insights)
- **Protocol**: MCP (Model Context Protocol) server — queryable from Claude Desktop
- **Database**: PostgreSQL (transactions, budgets, goals, health scores)

---

## Core Features

### 1. Transaction Management
- Upload bank CSV exports → AI auto-categorizes transactions
- Manual transaction entry via API
- Categories: food, transport, subscriptions, utilities, entertainment, savings, etc.

### 2. "What-If" Scenario Engine
- AI runs future projections based on spending changes
- Examples:
  - *"If I cut food delivery by 50%, when can I afford a MacBook Pro?"*
  - *"If I save ₹5000 extra/month, when do I hit my emergency fund goal?"*
- MCP tool: `run_scenario`

### 3. Subscription Intelligence Layer
- Auto-detects recurring charges from transaction history
- Tracks price changes on subscriptions
- AI scores each subscription by usage value
- MCP tools: `audit_subscriptions`, `flag_price_changes`

### 4. Proactive Financial Health Score
- Weekly score (0–100) based on: savings rate, budget adherence, subscription waste, unusual spends
- Background Celery job generates score + insight digest every week
- MCP tool: `get_health_score`

### 5. Budget & Goal Tracking
- Set monthly budgets per category
- Set savings goals with target amounts and deadlines
- AI tracks progress and alerts on overruns

---

## Architecture

```
User
  ↓
Claude Desktop / Chat UI
  ↓
[MCP Server]  ←→  FastAPI Backend
  ↓                    ↓
MCP Tools          PostgreSQL
  - get_spending        - transactions
  - compare_months      - budgets
  - run_scenario        - subscriptions
  - audit_subscriptions - health_scores
  - get_health_score    - goals
  - set_goal
  ↓
AI Layer (Claude API)
  - categorization
  - scenario simulation
  - weekly digest generation
```

---

## Key Directories (to be created)

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI route handlers (transactions, budgets, goals, health) |
| `app/services/` | Business logic (categorization, scenario engine, subscription detector) |
| `app/models/` | SQLAlchemy ORM models |
| `app/schemas/` | Pydantic request/response schemas |
| `mcp_server/` | Custom MCP server with all tools |
| `core/` | Config, DB sessions, dependencies |
| `celery_tasks/` | Weekly health score generation job |
| `migrations/` | Alembic database migrations |
| `tests/` | Pytest unit tests |

---

## MCP Tools to Implement

| Tool | Description |
|------|-------------|
| `get_spending` | Get spending by category and date range |
| `compare_months` | Compare spending between two months |
| `run_scenario` | Simulate what-if financial scenarios |
| `audit_subscriptions` | List detected subscriptions with waste scores |
| `flag_price_changes` | Detect subscriptions that increased in price |
| `get_health_score` | Get current financial health score with breakdown |
| `set_goal` | Create or update a savings goal |
| `get_goals` | List all goals with progress |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.100+ |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL |
| Cache/Broker | Redis |
| Background Jobs | Celery |
| AI | Claude API (claude-sonnet-4-6) |
| MCP | `mcp` Python SDK |
| Migrations | Alembic |
| Testing | pytest + pytest-cov |
| Linting | Ruff |

---

## Code Style Guidelines

- **Async/await** for all I/O (DB, HTTP, file)
- **Type hints** everywhere — all args and return types
- **Pydantic models** for all request/response schemas
- **No tuple returns** — use dataclasses or Pydantic models
- **Guard clauses** over nested ifs
- **Single responsibility** — split orchestration, parsing, and I/O into separate functions
- **Ruff** for formatting (120 char line length)
- **Conventional Commits**: `feat(transactions): add CSV upload endpoint`

---

## Environment Variables (to configure)

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/finsight
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=
MCP_SERVER_PORT=8001
API_PORT=8000
```

---

## Developer Notes

- The developer has strong FastAPI + async SQLAlchemy experience from a production project
- Familiar with Celery + Redis for background jobs
- First MCP server project — refer to the `mcp` Python SDK docs
- Target: ship MVP in 2-3 weeks
- Demo story: *"Upload 3 months of bank statements, ask what you're wasting money on — AI flags forgotten subscriptions and shows you could afford a Goa trip in 6 months by cutting food delivery by half"*

---

## Build Plan & Current Status

**Master build plan:** [`BUILD_PLAN.md`](BUILD_PLAN.md) — 11 phases, each with full checklists

**Phase docs:** [`docs/phases/`](docs/phases/) — one file per phase with commands, pros/cons, verification steps

**Architecture decisions:** [`docs/architecture-decisions.md`](docs/architecture-decisions.md) — why every major technical choice was made

**Known limitations:** [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — tracked gaps per phase, updated as we build

### Phase Status (update this as you complete phases)

| Phase | Title | Status |
|-------|-------|--------|
| 01 | Environment & Project Setup | ✅ Done |
| 02 | Core Infrastructure | ✅ Done |
| 03 | Transaction Management + Sessions + PDF | ✅ Done |
| 04 | Subscription Intelligence | ✅ Done |
| 05 | What-If Scenario Engine | ✅ Done |
| 06 | Financial Health Score | ⬜ Not started |
| 07 | Budget & Goal Tracking | ⬜ Not started |
| 08 | MCP Server Wiring | ⬜ Not started |
| 09 | Testing & Code Quality | ⬜ Not started |
| 10 | Deployment (Railway) | ⬜ Not started |
| 11 | Multi-User Support | ⬜ Not started |

### What is already shipped

These features are fully live — do NOT re-implement them:

**Phase 03 (Transactions + Sessions + PDF):**
- **Sessions** — `sessions` table, `session_id` FK on all owned tables, full CRUD API (`/api/v1/sessions/`). Each named session is an isolated data workspace (e.g. "hdfc credit card", "sbi savings"). Partial/case-insensitive name matching via `get_or_create_by_name`.
- **PDF import** — `POST /api/v1/transactions/import-pdf?session_id=`. Three-strategy parser: pdfplumber tables → Claude API → regex fallback. Lives in `app/services/pdf_parser.py`.
- **MCP tools:** `list_sessions`, `import_file(file_path, session_name)`, `delete_session(session_name)`, `get_spending(..., session_name="")`, `compare_months(..., session_name="")`. All tools resolve session from `FINSIGHT_SESSION` env var as default; `session_name` param overrides per-call.
- **Keyword categorizer fallback** — `app/services/categorizer.py` falls back to keyword matching when Claude API has no credits.
- **`FINSIGHT_SESSION` env var** — set in `.env` and `claude_desktop_config.json`. MCP server creates the named session if it doesn't exist.

**Phase 04 (Subscription Intelligence):**
- **`subscriptions` table** — session-scoped (`session_id` FK), stores name, pattern, latest/previous amount, frequency, waste score.
- **Detection service** — `subscription_service.detect_subscriptions(db, session_id)` — keyword-based matching (2+ occurrences = recurring), Claude waste scoring with graceful fallback.
- **API:** `POST /api/v1/subscriptions/detect?session_id=`, `GET /api/v1/subscriptions/?session_id=`, `GET /api/v1/subscriptions/price-changes?session_id=`.
- **MCP tools:** `detect_subscriptions(session_name="")`, `audit_subscriptions(session_name="")`, `flag_price_changes(session_name="")`.

**Phase 05 (What-If Scenario Engine):**
- **Scenario service** — `scenario_service.run_scenario(db, session_id, request)` — uses last 3 months of real spending as baseline, applies spending cuts, projects months to goal via Claude narrative + deterministic fallback.
- **API:** `POST /api/v1/scenarios/run?session_id=` (session_id optional; omit for cross-session).
- **MCP tool:** `run_scenario(category, reduction_pct, target_description, target_amount, extra_monthly_savings=0, session_name="")`.
- **Fallback** — `_deterministic_projection` runs when Claude API is unavailable.
- **Cross-session deduplication** — `app/utils/cross_session.py` detects inter-session transfers (e.g., "HDFC Credit Card Bill" in savings session) using session-name word overlap + payment keywords, and excludes them from cross-session aggregations. Applied automatically in `run_scenario` and `get_spending` when no session is specified. `get_spending_by_category` accepts `exclude_ids: frozenset[int]` parameter.

### Key data model note

`transactions.session_id` is a required FK to `sessions.id`. Every transaction belongs to exactly one session. All service functions take `session_id: uuid.UUID` as a parameter — never query transactions without it.

### Primary vs child sessions

The session named in `FINSIGHT_SESSION` (currently `"sbi savings"`) is the **primary/default session** — the main salary or savings account. All MCP tools default to this session when no `session_name` is given. `import_file` now accepts an optional `session_name`; leaving it empty imports into the primary account.

Child sessions (e.g. `"hdfc credit card"`, `"icici bank"`) are secondary accounts imported with explicit names. The cross-session deduplication in `app/utils/cross_session.py` ensures that credit card bill payments in the primary session are excluded when aggregating across all sessions, so card transactions are never double-counted.

**IMPORTANT for any Claude Code session:** Before writing any code, check which phase is current by reading the phase status above and the corresponding phase doc in `docs/phases/`. Do not implement anything outside the current phase scope.

---

## Key Design Decisions (summary)

Full reasoning in [`docs/architecture-decisions.md`](docs/architecture-decisions.md).

| Decision | Choice | One-line reason |
|----------|--------|-----------------|
| Web framework | FastAPI | Native async, auto Swagger, Pydantic v2 |
| DB | PostgreSQL | NUMERIC for money, asyncpg, Alembic |
| ORM | SQLAlchemy 2.0 async | Industry standard, Alembic integration |
| Migrations | Alembic | Versioned, reversible, autogenerate |
| Background jobs | Celery + Redis | Battle-tested periodic jobs |
| AI | claude-sonnet-4-6 | Native MCP support, best cost/quality |
| Dep management | pip-compile | Pinned transitive deps |
| Linting | Ruff | Replaces flake8+isort+pyupgrade, 100x faster |
| Build order | Vertical slices | Integration bugs surface per feature, not at the end |
| Deployment | Railway | Native Postgres+Redis, doesn't sleep, $0-5/month |

---

## Estimated Costs

- **Anthropic API:** < $0.20/month at personal use scale
- **Railway hosting:** $0–$5/month (usually within free credit)
- **Total: effectively $0 during development; $0–$5/month deployed**

# Architecture & Design Decisions

This document captures the **why** behind every major technical choice in FinSight. Each decision includes the alternatives considered, trade-offs, and the final verdict with reasoning.

---

## 1. Language & Runtime — Python 3.11

**Alternatives considered:** Node.js, Go, Python 3.10

**Why Python 3.11:**
- Best-in-class Anthropic SDK support (official Python SDK)
- FastAPI is Python-native and the fastest option for async Python APIs
- asyncio + asyncpg is a proven async DB stack
- 3.11 gives significant performance improvements over 3.10 (up to 25% faster CPython)
- `tomllib` built-in (no extra dep for pyproject.toml parsing)

**Trade-offs:** Python is slower than Go/Rust, but this is an I/O-bound app (DB + Claude API calls dominate). CPU speed is irrelevant here.

---

## 2. Web Framework — FastAPI

**Alternatives considered:** Django REST Framework, Flask, Litestar

**Why FastAPI:**
- Native async/await — essential for non-blocking DB + AI API calls
- Automatic OpenAPI/Swagger docs (zero config) — critical for dev iteration
- Pydantic v2 integration — request validation, response serialization, and schema generation in one
- Dependency injection system makes DB session management clean
- Actively maintained; largest async Python API ecosystem

**Why not Django:** Django ORM doesn't support async natively; async Django is complex and not idiomatic.
**Why not Flask:** Sync-first; async support is bolted on; no built-in validation.

**Design pattern used:** Application factory pattern (`create_app()`) — allows the app to be instantiated fresh in tests with dependency overrides, avoiding global state issues.

---

## 3. Database — PostgreSQL 15

**Alternatives considered:** SQLite, MySQL, MongoDB

**Why PostgreSQL:**
- First-class `asyncpg` driver with excellent async performance
- `NUMERIC(12,2)` type for money — no floating-point rounding errors (critical for finance)
- `ENUM` types for categories — enforced at DB level, not just application level
- Window functions, CTEs, and advanced aggregations for spending analytics
- `UNIQUE` constraints for idempotent upserts (budget, health score)
- Industry standard for financial data

**Why not SQLite:** asyncpg doesn't support SQLite; SQLite's type system is too loose for financial data.
**Why not MongoDB:** Financial data is highly relational (transactions → budgets → goals). Document DB is the wrong shape.

**Schema design patterns used:**
- **Normalized** — one row per entity, no JSON blobs (except `waste_reason` which is free text)
- **Unique constraints for upserts** — `(category, month, year)` on budgets; `(year, week)` on health scores
- **Enum columns** — `TransactionCategory` stored as DB enum, not string

---

## 4. ORM — SQLAlchemy 2.0 (Async)

**Alternatives considered:** Tortoise ORM, Databases, raw asyncpg, SQLModel

**Why SQLAlchemy 2.0:**
- Industry standard; best documentation and community
- `mapped_column` + `Mapped[type]` gives proper Python type inference (2.0 style)
- `async_sessionmaker` + `AsyncSession` is production-grade async
- Alembic (migrations) is a first-party companion — deeply integrated
- `expire_on_commit=False` prevents lazy-load errors in async context

**Why not Tortoise ORM:** Smaller community; less mature migration story.
**Why not SQLModel:** SQLModel is a thin wrapper over SQLAlchemy that adds constraints without much benefit; SQLAlchemy directly gives more control.

**Patterns used:**
- **Repository pattern (lightweight):** Service functions receive a `db: AsyncSession` — DB operations stay in services, not routes
- **Dependency injection for sessions:** `get_db()` as FastAPI dependency — clean per-request session lifecycle
- `expire_on_commit=False` — critical for async SQLAlchemy; avoids "instance not bound to session" errors after commit

---

## 5. Migrations — Alembic

**Alternatives considered:** SQLAlchemy `create_all()`, Aerich (Tortoise), raw SQL files

**Why Alembic:**
- First-party SQLAlchemy companion — autogenerate detects model changes
- Versioned, reversible migrations — critical even for personal projects
- async-compatible with `create_async_engine`
- `alembic upgrade head` as Dockerfile CMD ensures migrations run before app starts

**Why not `create_all()`:** No history, no rollbacks, dangerous in any environment with existing data.

**Pattern used:** `env.py` imports all models via `app.models.__init__` — single import point ensures Alembic sees the full schema. Adding a new model = one line in `app/models/__init__.py`.

---

## 6. Async Runtime — asyncio + asyncpg

**Alternatives considered:** Trio, gevent, threading

**Why asyncio:**
- Native Python async runtime; FastAPI is built on it
- asyncpg is the fastest Postgres driver for Python — benchmarks show 3x faster than psycopg2 for async workloads
- Celery uses threads internally; asyncio handles everything else

**Why asyncpg over psycopg3:** asyncpg is more mature and better tested for SQLAlchemy async; psycopg3 async is newer and has less production track record.

**Key pattern:** `pool_pre_ping=True` on the engine — checks connection health before use; prevents "connection closed" errors after idle periods.

---

## 7. Background Jobs — Celery + Redis

**Alternatives considered:** APScheduler, FastAPI background tasks, Python `schedule` library, Temporal

**Why Celery:**
- Battle-tested for exactly this use case: periodic jobs (weekly health score)
- Redis as both broker and result backend — no extra dependencies
- Celery beat handles cron-style scheduling natively
- Can be scaled to multiple workers without code changes

**Why not FastAPI background tasks:** They run in-process; no persistence, no retry, no scheduling.
**Why not APScheduler:** Fine for simple cases but lacks Celery's observability and retry semantics.
**Why not Temporal:** Massively over-engineered for a single weekly job.

**Pattern used:** Task defined in `celery_tasks/` module, uses `asyncio.run()` to bridge sync Celery world into async SQLAlchemy world. This is the standard pattern for async-in-Celery.

---

## 8. AI Integration — Anthropic SDK (Claude)

**Alternatives considered:** OpenAI GPT-4, local LLM (Ollama), Gemini

**Why Claude (claude-sonnet-4-6):**
- Native MCP protocol support — Claude Desktop integrates via MCP out of the box
- Anthropic SDK is first-party and well-maintained
- claude-sonnet-4-6 is the sweet spot of cost vs. capability for categorization + reasoning
- Structured output (JSON responses) is reliable with proper system prompts

**Why not GPT-4:** No native MCP support; would require a separate MCP adapter.
**Why not local LLM:** Categorization quality is noticeably worse; harder to deploy.

**Usage patterns:**
- **Batch categorization:** Send 50 transactions at once → one API call instead of 50
- **Claude for narrative, Python for numbers:** Health scores computed deterministically; Claude writes the digest. This makes scores testable and reproducible.
- **Structured JSON responses:** All Claude calls specify JSON output format in system prompt — avoids text parsing complexity.
- **AsyncAnthropic client:** Single module-level instance reused across all calls (`client = AsyncAnthropic(...)`) — avoids connection overhead per request.

---

## 9. MCP Server — `mcp` Python SDK

**Alternatives considered:** Build custom JSON-RPC server, use LangChain tools, use OpenAI function calling

**Why MCP:**
- Native Claude Desktop integration — no extra adapter needed
- The `mcp` Python SDK handles all protocol details (tool registration, input validation, stdio transport)
- Tools are plain Python async functions — no framework-specific abstractions
- stdio transport is zero-config for Claude Desktop

**Design pattern:** `register_*_tools(server)` functions per feature — each feature registers its tools independently. The main `server.py` assembles them. This keeps tool logic co-located with the feature it serves.

---

## 10. Dependency Management — pip-compile

**Alternatives considered:** Poetry, PDM, pipenv, plain pip

**Why pip-compile:**
- Pins all transitive dependencies — reproducible installs across environments
- `requirements.in` = what you depend on; `requirements.txt` = exactly what gets installed
- Works with plain pip — no new tool to learn
- `pip-compile --upgrade` for controlled upgrades

**Why not Poetry:** Poetry is good but adds complexity (lockfile format, separate resolver) that isn't needed here. pip-compile is simpler and production-tested at scale.

---

## 11. Linting — Ruff

**Alternatives considered:** flake8 + isort + black, pylint

**Why Ruff:**
- Replaces flake8 + isort + pyupgrade in one tool, written in Rust — 100x faster
- Auto-fix mode (`--fix`) handles import sorting and simple style issues automatically
- 120-char line length matches the project's actual code style

---

## 12. Testing Strategy

**Pattern: Arrange-Act-Assert with real DB, mocked Claude API**

| Layer | Strategy |
|---|---|
| Service logic | Real Postgres test DB; mock Claude API calls |
| API routes | `AsyncClient` + `ASGITransport` with test DB override |
| MCP tools | Not unit-tested separately — covered by API + service tests |
| Celery tasks | Not unit-tested — integration tested by calling service directly |

**Why mock Claude but not DB:** Claude is an external paid service — real calls in tests would be expensive, slow, and non-deterministic. The DB is local, free, and deterministic.

**Test DB isolation:** Each test rolls back in `finally` — no test data bleeds between tests. Session-scoped engine creation amortizes the `CREATE TABLE` cost across the test run.

---

## 13. Deployment Architecture

```
Internet
    ↓
Railway (FastAPI + Uvicorn)     Railway (Celery Worker)
    ↓                               ↓
Railway PostgreSQL  ←————————————→  Railway Redis
    ↑
MCP Server (local, via stdio or ngrok)
    ↑
Claude Desktop
```

**Why not Kubernetes / ECS:** Massively over-engineered for a personal demo project. Railway provides managed Postgres + Redis with zero ops overhead.

**Why Dockerfile over buildpacks:** Need `alembic upgrade head` to run before the app starts — hard to express in buildpack Procfile semantics. Dockerfile CMD chains migration + server start cleanly.

---

## 14. Vertical Slice Build Order

**Pattern:** Build one full feature end-to-end (model → service → API → MCP → tests) before starting the next.

**Why not horizontal layers:** Horizontal layering (all models first, then all services, etc.) defers integration testing. With vertical slices, each phase ends with a working, testable feature. Bugs at integration points surface immediately rather than 3 phases later.

**Order rationale:**
1. **Transactions first** — everything else depends on transaction data
2. **Subscriptions second** — reads from transactions; builds the "waste detection" story
3. **Scenarios third** — reads from transactions; completes the demo story early
4. **Health score fourth** — aggregates transactions + subscriptions; Celery job
5. **Budgets/Goals fifth** — enriches health score; self-contained
6. **MCP wiring sixth** — all tools exist; just wire and configure Claude Desktop
7. **Testing/CI seventh** — lock in quality gates after features are stable
8. **Deployment last** — deploy working, tested code

---

## 15. Currency & Locale

**Decision:** Store amounts as `NUMERIC(12,2)` (2 decimal places), display with ₹ symbol, no currency conversion.

**Why NUMERIC not FLOAT:** Floating-point arithmetic loses precision with money. `Decimal("0.1") + Decimal("0.2") == Decimal("0.3")` — floats can't guarantee this.

**Why not store in paise (smallest unit):** Unnecessary complexity for personal use; 2 decimal places is sufficient.

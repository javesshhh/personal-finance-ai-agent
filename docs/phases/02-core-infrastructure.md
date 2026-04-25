# Phase 02 — Core Infrastructure

## Overview

This phase wires up the foundational plumbing that every feature will build on: async SQLAlchemy engine, Alembic migrations, FastAPI app factory, Celery worker, and a health-check endpoint. No business logic yet — just a working skeleton you can prove is alive.

**Why this order:** Getting DB connections, migrations, and the app factory right before writing models means you never have to fight migration state while also debugging business logic.

---

## Pros / Cons of Key Decisions

### Decision: Async SQLAlchemy (`asyncpg`) vs. sync SQLAlchemy (`psycopg2`)

| | Async (`asyncpg`) | Sync (`psycopg2`) |
|---|---|---|
| **Pro** | Non-blocking I/O; fits FastAPI's async model; no thread pool overhead | Simpler, more examples online |
| **Con** | Slightly more boilerplate; `asyncpg` driver instead of `psycopg2` | Blocks the event loop; bad for FastAPI throughput |
| **Verdict** | ✅ Async — this is a FastAPI project, blocking I/O would negate the entire async stack |

### Decision: Alembic for migrations vs. SQLAlchemy `create_all`

| | Alembic | `create_all` |
|---|---|---|
| **Pro** | Versioned, reversible, tracks schema history | Zero setup |
| **Con** | More initial setup | No migration history, can't roll back, dangerous in prod |
| **Verdict** | ✅ Alembic — always, even for personal projects. Trains the right habits. |

### Decision: FastAPI `lifespan` context manager vs. `startup`/`shutdown` events

| | `lifespan` | `@app.on_event` |
|---|---|---|
| **Pro** | Modern, recommended in FastAPI 0.93+; single function, clear scope | Familiar older pattern |
| **Con** | Less googling material | Deprecated in newer FastAPI |
| **Verdict** | ✅ Use `lifespan` — it's the current standard |

---

## Checklist

### 1. Create async database engine and session factory

- [ ] Create `core/database.py`:
  ```python
  from collections.abc import AsyncGenerator

  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
  from sqlalchemy.orm import DeclarativeBase

  from core.config import settings

  engine = create_async_engine(
      settings.database_url,
      echo=settings.environment == "development",
      pool_pre_ping=True,
  )

  AsyncSessionLocal = async_sessionmaker(
      bind=engine,
      class_=AsyncSession,
      expire_on_commit=False,
  )


  class Base(DeclarativeBase):
      pass


  async def get_db() -> AsyncGenerator[AsyncSession, None]:
      async with AsyncSessionLocal() as session:
          yield session
  ```
- [ ] Verify it imports cleanly:
  ```bash
  python -c "from core.database import engine, Base; print('DB engine OK')"
  ```

---

### 2. Initialize Alembic

- [ ] Initialize Alembic in the project root:
  ```bash
  alembic init migrations
  ```
- [ ] Edit `alembic.ini` — comment out the `sqlalchemy.url` line (we'll set it dynamically):
  ```ini
  # sqlalchemy.url = driver://user:pass@localhost/dbname
  ```
- [ ] Edit `migrations/env.py` — replace the entire file with async-aware config:
  ```python
  import asyncio
  from logging.config import fileConfig

  from alembic import context
  from sqlalchemy.ext.asyncio import create_async_engine

  from core.config import settings
  from core.database import Base

  # Import all models so Alembic can detect them
  import app.models  # noqa: F401

  config = context.config
  if config.config_file_name is not None:
      fileConfig(config.config_file_name)

  target_metadata = Base.metadata


  def run_migrations_offline() -> None:
      context.configure(
          url=settings.database_url,
          target_metadata=target_metadata,
          literal_binds=True,
          dialect_opts={"paramstyle": "named"},
      )
      with context.begin_transaction():
          context.run_migrations()


  async def run_migrations_online() -> None:
      connectable = create_async_engine(settings.database_url)
      async with connectable.connect() as connection:
          await connection.run_sync(
              lambda conn: context.configure(connection=conn, target_metadata=target_metadata)
          )
          async with connection.begin():
              await connection.run_sync(lambda _: context.run_migrations())


  if context.is_offline_mode():
      run_migrations_offline()
  else:
      asyncio.run(run_migrations_online())
  ```
- [ ] Create `app/models/__init__.py` that will import all models (empty for now, you'll add imports as you build):
  ```python
  # Import all models here so Alembic can detect them
  # e.g. from app.models.transaction import Transaction
  ```
- [ ] Verify Alembic can connect and see the (empty) metadata:
  ```bash
  alembic current
  # Should print: INFO [alembic.runtime.migration] Context impl PostgresqlImpl.
  # No revision yet — that's expected
  ```

---

### 3. Create the FastAPI application factory

- [ ] Create `core/app.py`:
  ```python
  from contextlib import asynccontextmanager

  from fastapi import FastAPI

  from core.database import engine


  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Startup
      yield
      # Shutdown
      await engine.dispose()


  def create_app() -> FastAPI:
      app = FastAPI(
          title="FinSight",
          description="Personal Finance Intelligence Agent",
          version="0.1.0",
          lifespan=lifespan,
      )

      # Register routers here as you build them
      # from api.transactions import router as transactions_router
      # app.include_router(transactions_router, prefix="/api/v1")

      return app
  ```
- [ ] Create the main entrypoint `main.py` in project root:
  ```python
  import uvicorn

  from core.app import create_app
  from core.config import settings

  app = create_app()

  if __name__ == "__main__":
      uvicorn.run(
          "main:app",
          host="0.0.0.0",
          port=settings.api_port,
          reload=settings.environment == "development",
      )
  ```

---

### 4. Add health-check endpoint

- [ ] Create `api/health.py`:
  ```python
  from fastapi import APIRouter, Depends
  from sqlalchemy import text
  from sqlalchemy.ext.asyncio import AsyncSession

  from core.database import get_db

  router = APIRouter(tags=["health"])


  @router.get("/health")
  async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
      await db.execute(text("SELECT 1"))
      return {"status": "ok", "database": "connected"}
  ```
- [ ] Register the health router in `core/app.py`:
  ```python
  from api.health import router as health_router
  # inside create_app():
  app.include_router(health_router)
  ```
- [ ] Start the server and test:
  ```bash
  python main.py
  # In another terminal:
  curl http://localhost:8000/health
  # Expected: {"status":"ok","database":"connected"}
  ```

---

### 5. Set up Celery

- [ ] Create `core/celery_app.py`:
  ```python
  from celery import Celery

  from core.config import settings

  celery_app = Celery(
      "finsight",
      broker=settings.redis_url,
      backend=settings.redis_url,
      include=["celery_tasks.health_score"],
  )

  celery_app.conf.update(
      task_serializer="json",
      result_serializer="json",
      accept_content=["json"],
      timezone="UTC",
      enable_utc=True,
  )
  ```
- [ ] Create `celery_tasks/__init__.py` (already created, leave empty)
- [ ] Create a placeholder `celery_tasks/health_score.py` (will be filled in Phase 06):
  ```python
  from core.celery_app import celery_app


  @celery_app.task(name="generate_health_score")
  def generate_health_score(user_id: int) -> dict:
      # Implemented in Phase 06
      return {"status": "not_implemented"}
  ```
- [ ] Verify Celery starts without error:
  ```bash
  celery -A core.celery_app.celery_app worker --loglevel=info &
  # Should print "ready" — Ctrl+C to stop, or kill the background job
  ```

---

### 6. Create `app/models/__init__.py` import scaffold

- [ ] This file will grow as you add models. The pattern for each new model is:
  ```python
  # Add one line per model as you build phases 03–07:
  # from app.models.transaction import Transaction
  # from app.models.subscription import Subscription
  # from app.models.health_score import HealthScore
  # from app.models.budget import Budget
  # from app.models.goal import Goal
  ```
  Leave it as comments for now — you'll uncomment as you go.

---

### 7. Run first (empty) Alembic migration to verify the pipeline works

- [ ] Generate the initial migration:
  ```bash
  alembic revision --autogenerate -m "initial"
  ```
  Expected: creates `migrations/versions/<hash>_initial.py` with empty `upgrade()` / `downgrade()`
- [ ] Apply it:
  ```bash
  alembic upgrade head
  ```
- [ ] Verify migration tracking table exists:
  ```bash
  psql postgresql://finsight:finsight@localhost:5432/finsight \
    -c "SELECT version_num FROM alembic_version;"
  # Should print the revision hash
  ```

---

## Verification — Phase 02 Complete

- [ ] `curl http://localhost:8000/health` → `{"status":"ok","database":"connected"}`
- [ ] `curl http://localhost:8000/docs` → FastAPI Swagger UI loads in browser
- [ ] `alembic current` → shows the initial revision hash
- [ ] `celery -A core.celery_app.celery_app worker --loglevel=info` → starts without errors
- [ ] `ruff check .` → no errors
- [ ] All files committed to git:
  ```bash
  git add -A
  git commit -m "feat(infra): add core infrastructure — DB engine, Alembic, FastAPI factory, Celery"
  ```

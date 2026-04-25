# Phase 09 — Testing & Code Quality

## Overview

This phase locks in quality gates: comprehensive test coverage, Ruff linting, and a GitHub Actions CI pipeline. Every future change must pass these gates before it's considered shippable.

**Why last among features:** Tests written after each feature (Phases 03–08) cover service logic. This phase adds integration-level tests, coverage config, and the CI pipeline that enforces everything automatically.

---

## Pros / Cons of Key Decisions

### Decision: pytest-asyncio vs. `asynctest`

| | pytest-asyncio | asynctest |
|---|---|---|
| **Pro** | Actively maintained; `asyncio_mode="auto"` removes boilerplate; first-class pytest plugin | Older, less maintained |
| **Con** | Requires `asyncio_mode` config to avoid decorating every test | — |
| **Verdict** | ✅ pytest-asyncio — the standard for modern async Python testing |

### Decision: Real test DB vs. SQLite in-memory vs. mock everything

| | Real Postgres test DB | SQLite in-memory | Mock everything |
|---|---|---|---|
| **Pro** | Tests actual SQL behavior; catches dialect-specific bugs | Fast, no Docker needed | Fastest |
| **Con** | Requires Docker; slightly slower | SQLite != Postgres; asyncpg won't work | Mocks lie; misses integration bugs |
| **Verdict** | ✅ Real Postgres test DB (`finsight_test`) — you already have Docker running, and asyncpg requires Postgres |

### Decision: Coverage threshold — 80% vs. 90% vs. no threshold

| | 80% | 90% | None |
|---|---|---|---|
| **Pro** | Achievable without over-testing trivial code | High confidence | Zero friction |
| **Con** | May leave critical paths untested | Hard to maintain for complex features | Regressions slip in silently |
| **Verdict** | ✅ 80% — enough for a personal project without becoming a testing tax |

---

## Checklist

### 1. Finalize `conftest.py` with full fixtures

- [ ] Update `tests/conftest.py` to include all fixtures needed across tests:
  ```python
  import pytest
  import pytest_asyncio
  from httpx import ASGITransport, AsyncClient
  from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

  import app.models  # noqa: F401 — registers all models with Base
  from core.app import create_app
  from core.database import Base, get_db

  TEST_DATABASE_URL = "postgresql+asyncpg://finsight:finsight@localhost:5432/finsight_test"


  @pytest_asyncio.fixture(scope="session")
  async def engine():
      eng = create_async_engine(TEST_DATABASE_URL)
      async with eng.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)
      yield eng
      async with eng.begin() as conn:
          await conn.run_sync(Base.metadata.drop_all)
      await eng.dispose()


  @pytest_asyncio.fixture
  async def db_session(engine):
      factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
      async with factory() as session:
          yield session
          await session.rollback()


  @pytest_asyncio.fixture
  async def client(engine):
      """HTTP test client with DB overridden to use test database."""
      factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

      async def override_get_db():
          async with factory() as session:
              yield session

      app = create_app()
      app.dependency_overrides[get_db] = override_get_db

      async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
          yield ac
  ```

---

### 2. Write API-level integration tests

- [ ] Create `tests/test_api_transactions.py`:
  ```python
  import pytest


  @pytest.mark.asyncio
  async def test_health_check(client):
      response = await client.get("/health")
      assert response.status_code == 200
      assert response.json()["status"] == "ok"


  @pytest.mark.asyncio
  async def test_create_transaction(client):
      response = await client.post(
          "/api/v1/transactions/",
          json={"date": "2024-01-15", "description": "Coffee", "amount": -150.0, "category": "food"},
      )
      assert response.status_code == 201
      data = response.json()
      assert data["id"] is not None
      assert data["category"] == "food"


  @pytest.mark.asyncio
  async def test_create_transaction_zero_amount_rejected(client):
      response = await client.post(
          "/api/v1/transactions/",
          json={"date": "2024-01-15", "description": "Zero", "amount": 0, "category": "food"},
      )
      assert response.status_code == 422


  @pytest.mark.asyncio
  async def test_import_csv_bad_columns(client):
      csv_content = b"name,value\nSwiggy,450"
      response = await client.post(
          "/api/v1/transactions/import-csv",
          files={"file": ("bad.csv", csv_content, "text/csv")},
      )
      assert response.status_code == 422
  ```
- [ ] Create `tests/test_api_budgets.py`:
  ```python
  import pytest


  @pytest.mark.asyncio
  async def test_create_budget(client):
      response = await client.post(
          "/api/v1/budgets/",
          json={"category": "food", "month": 1, "year": 2024, "limit_amount": 5000.0},
      )
      assert response.status_code == 200
      data = response.json()
      assert data["limit_amount"] == "5000.00"
      assert data["is_over_budget"] is False


  @pytest.mark.asyncio
  async def test_create_budget_invalid_month(client):
      response = await client.post(
          "/api/v1/budgets/",
          json={"category": "food", "month": 13, "year": 2024, "limit_amount": 5000.0},
      )
      assert response.status_code == 422
  ```
- [ ] Run all tests:
  ```bash
  pytest tests/ -v
  ```

---

### 3. Configure coverage

- [ ] Update `pyproject.toml` with coverage settings:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  addopts = "--cov=app --cov=api --cov=mcp_server --cov-report=term-missing --cov-fail-under=80"

  [tool.coverage.run]
  omit = ["tests/*", "migrations/*", "scripts/*"]

  [tool.coverage.report]
  exclude_lines = [
      "pragma: no cover",
      "if __name__ == .__main__.:",
      "raise NotImplementedError",
  ]
  ```
- [ ] Run with coverage:
  ```bash
  pytest tests/ --cov=app --cov-report=html
  open htmlcov/index.html  # View in browser
  ```

---

### 4. Set up GitHub Actions CI

- [ ] Create `.github/workflows/ci.yml`:
  ```yaml
  name: CI

  on:
    push:
      branches: [main]
    pull_request:
      branches: [main]

  jobs:
    test:
      runs-on: ubuntu-latest

      services:
        postgres:
          image: postgres:15-alpine
          env:
            POSTGRES_USER: finsight
            POSTGRES_PASSWORD: finsight
            POSTGRES_DB: finsight_test
          ports:
            - 5432:5432
          options: >-
            --health-cmd pg_isready
            --health-interval 10s
            --health-timeout 5s
            --health-retries 5

        redis:
          image: redis:7-alpine
          ports:
            - 6379:6379
          options: >-
            --health-cmd "redis-cli ping"
            --health-interval 10s
            --health-timeout 5s
            --health-retries 5

      env:
        DATABASE_URL: postgresql+asyncpg://finsight:finsight@localhost:5432/finsight
        REDIS_URL: redis://localhost:6379
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      steps:
        - uses: actions/checkout@v4

        - uses: actions/setup-python@v5
          with:
            python-version: "3.11"
            cache: pip

        - name: Install dependencies
          run: pip install -r requirements_dev.txt

        - name: Lint with Ruff
          run: ruff check .

        - name: Run migrations
          run: alembic upgrade head

        - name: Run tests
          run: pytest tests/ -v --cov=app --cov-fail-under=80
  ```
- [ ] Create `.github/` directory:
  ```bash
  mkdir -p .github/workflows
  ```
- [ ] Add `ANTHROPIC_API_KEY` to GitHub repo secrets:
  - Go to repo → Settings → Secrets and variables → Actions → New repository secret
  - Name: `ANTHROPIC_API_KEY`, Value: your key

---

### 5. Add pre-commit hooks (optional but recommended)

- [ ] Add `pre-commit` to `requirements_dev.in`:
  ```
  pre-commit>=3.5.0
  ```
- [ ] Recompile:
  ```bash
  pip-compile requirements_dev.in -o requirements_dev.txt
  pip install pre-commit
  ```
- [ ] Create `.pre-commit-config.yaml`:
  ```yaml
  repos:
    - repo: https://github.com/astral-sh/ruff-pre-commit
      rev: v0.1.9
      hooks:
        - id: ruff
          args: [--fix]
    - repo: https://github.com/pre-commit/pre-commit-hooks
      rev: v4.5.0
      hooks:
        - id: trailing-whitespace
        - id: end-of-file-fixer
        - id: check-yaml
        - id: check-json
  ```
- [ ] Install hooks:
  ```bash
  pre-commit install
  ```
- [ ] Run against all files once:
  ```bash
  pre-commit run --all-files
  ```

---

## Verification — Phase 09 Complete

- [ ] `pytest tests/ -v` → all tests pass
- [ ] `pytest tests/ --cov=app --cov-fail-under=80` → coverage ≥ 80%
- [ ] `ruff check .` → no errors
- [ ] Push to GitHub → CI pipeline passes (green checkmark)
- [ ] `pre-commit run --all-files` → no failures
- [ ] Commit:
  ```bash
  git add -A
  git commit -m "test(ci): add full test suite, coverage config, GitHub Actions CI, and pre-commit hooks"
  ```

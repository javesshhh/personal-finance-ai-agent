# Phase 01 — Environment & Project Setup

## Overview

This phase gets your local development environment fully operational before a single line of application code is written. Doing this right means every subsequent phase starts from a known-good baseline — no "works on my machine" surprises mid-build.

**Why this order:** Infrastructure mistakes (wrong Python version, missing env vars, broken DB connection) compound fast. Catching them in Phase 01 saves hours later.

---

## Pros / Cons of Key Decisions

### Decision: Docker for Postgres + Redis vs. local installs

| | Docker | Local install |
|---|---|---|
| **Pro** | Identical env across machines; easy to nuke and recreate | Faster startup, no Docker overhead |
| **Con** | Requires Docker Desktop running; slightly slower cold start | Version drift risk; harder to reset cleanly |
| **Verdict** | ✅ Use Docker — `docker-compose.yml` keeps deps reproducible |

### Decision: `venv` vs. `conda` vs. `pyenv` + `venv`

| | venv only | pyenv + venv |
|---|---|---|
| **Pro** | Simpler, built into Python | Pin exact Python version per project |
| **Con** | Relies on system Python being 3.11 | Extra tool to install |
| **Verdict** | ✅ Use `pyenv + venv` — guarantees Python 3.11 regardless of system Python |

### Decision: `requirements.in` + `pip-compile` vs. plain `requirements.txt`

| | pip-compile | Plain requirements.txt |
|---|---|---|
| **Pro** | Pinned transitive deps, reproducible installs, easy upgrades | Simpler |
| **Con** | Extra step (`pip-compile`) | Unpinned transitive deps can silently break |
| **Verdict** | ✅ Use `pip-compile` — production-grade dep management from day one |

---

## Checklist

### 1. Install system prerequisites

- [ ] Install [pyenv](https://github.com/pyenv/pyenv) if not already installed:
  ```bash
  brew install pyenv
  echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
  echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
  echo 'eval "$(pyenv init -)"' >> ~/.zshrc
  source ~/.zshrc
  ```
- [ ] Install Python 3.11:
  ```bash
  pyenv install 3.11.9
  pyenv local 3.11.9
  python --version  # should print Python 3.11.9
  ```
- [ ] Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) if not already installed
- [ ] Verify Docker is running:
  ```bash
  docker --version
  docker compose version
  ```
- [ ] Install `pip-tools`:
  ```bash
  pip install pip-tools
  ```

---

### 2. Create project virtual environment

- [ ] From the project root, create and activate venv:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  ```
- [ ] Confirm you're in the venv:
  ```bash
  which python  # should show .venv/bin/python
  ```
- [ ] Add `.venv/` to `.gitignore`:
  ```bash
  echo ".venv/" >> .gitignore
  echo "__pycache__/" >> .gitignore
  echo "*.pyc" >> .gitignore
  echo ".env" >> .gitignore
  echo "*.egg-info/" >> .gitignore
  echo ".pytest_cache/" >> .gitignore
  echo ".ruff_cache/" >> .gitignore
  echo "htmlcov/" >> .gitignore
  echo ".coverage" >> .gitignore
  ```

---

### 3. Create project directory structure

- [ ] Scaffold the full directory tree:
  ```bash
  mkdir -p api
  mkdir -p app/services
  mkdir -p app/models
  mkdir -p app/schemas
  mkdir -p mcp_server
  mkdir -p core
  mkdir -p celery_tasks
  mkdir -p migrations
  mkdir -p tests
  mkdir -p docs/phases
  ```
- [ ] Create `__init__.py` files for all Python packages:
  ```bash
  touch api/__init__.py
  touch app/__init__.py
  touch app/services/__init__.py
  touch app/models/__init__.py
  touch app/schemas/__init__.py
  touch mcp_server/__init__.py
  touch core/__init__.py
  touch celery_tasks/__init__.py
  touch tests/__init__.py
  ```
- [ ] Verify structure:
  ```bash
  find . -type f -name "*.py" | sort
  ```

---

### 4. Create `requirements.in` with all dependencies

- [ ] Create `requirements.in`:
  ```
  # Web framework
  fastapi>=0.100.0
  uvicorn[standard]>=0.23.0

  # Database
  sqlalchemy[asyncio]>=2.0.0
  asyncpg>=0.28.0
  alembic>=1.12.0

  # Redis & Celery
  redis>=5.0.0
  celery[redis]>=5.3.0

  # AI
  anthropic>=0.25.0

  # MCP
  mcp>=1.0.0

  # Utilities
  python-multipart>=0.0.6
  python-dotenv>=1.0.0
  pydantic>=2.0.0
  pydantic-settings>=2.0.0
  httpx>=0.25.0
  ```
- [ ] Create `requirements_dev.in`:
  ```
  -r requirements.in

  # Testing
  pytest>=7.4.0
  pytest-asyncio>=0.21.0
  pytest-cov>=4.1.0
  httpx>=0.25.0

  # Linting
  ruff>=0.1.0

  # Dev tools
  ipython>=8.0.0
  ```
- [ ] Compile pinned lock files:
  ```bash
  pip-compile requirements.in -o requirements.txt
  pip-compile requirements_dev.in -o requirements_dev.txt
  ```
- [ ] Install dev dependencies:
  ```bash
  pip install -r requirements_dev.txt
  ```
- [ ] Verify key packages installed:
  ```bash
  python -c "import fastapi, sqlalchemy, anthropic, mcp; print('All imports OK')"
  ```

---

### 5. Create Docker Compose for Postgres + Redis

- [ ] Create `docker-compose.yml` in project root:
  ```yaml
  version: "3.9"

  services:
    postgres:
      image: postgres:15-alpine
      container_name: finsight_postgres
      environment:
        POSTGRES_USER: finsight
        POSTGRES_PASSWORD: finsight
        POSTGRES_DB: finsight
      ports:
        - "5432:5432"
      volumes:
        - postgres_data:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U finsight"]
        interval: 5s
        timeout: 5s
        retries: 5

    redis:
      image: redis:7-alpine
      container_name: finsight_redis
      ports:
        - "6379:6379"
      healthcheck:
        test: ["CMD", "redis-cli", "ping"]
        interval: 5s
        timeout: 5s
        retries: 5

  volumes:
    postgres_data:
  ```
- [ ] Start services:
  ```bash
  docker compose up -d
  ```
- [ ] Verify both are healthy:
  ```bash
  docker compose ps
  # Both should show "healthy"
  ```

---

### 6. Create `.env` file

- [ ] Create `.env` in project root (already in `.gitignore`):
  ```env
  DATABASE_URL=postgresql+asyncpg://finsight:finsight@localhost:5432/finsight
  REDIS_URL=redis://localhost:6379
  ANTHROPIC_API_KEY=your_key_here
  MCP_SERVER_PORT=8001
  API_PORT=8000
  ENVIRONMENT=development
  ```
- [ ] Create `.env.example` (safe to commit — no real secrets):
  ```env
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/finsight
  REDIS_URL=redis://localhost:6379
  ANTHROPIC_API_KEY=your_anthropic_api_key_here
  MCP_SERVER_PORT=8001
  API_PORT=8000
  ENVIRONMENT=development
  ```
- [ ] Commit `.env.example`:
  ```bash
  git add .env.example
  ```

---

### 7. Create `core/config.py` — settings loader

- [ ] Create `core/config.py`:
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict


  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", extra="ignore")

      database_url: str
      redis_url: str
      anthropic_api_key: str
      mcp_server_port: int = 8001
      api_port: int = 8000
      environment: str = "development"


  settings = Settings()
  ```
- [ ] Verify it loads without error:
  ```bash
  python -c "from core.config import settings; print(settings.database_url)"
  ```

---

### 8. Configure Ruff linter

- [ ] Create `pyproject.toml`:
  ```toml
  [tool.ruff]
  line-length = 120
  target-version = "py311"

  [tool.ruff.lint]
  select = ["E", "F", "I", "N", "W", "UP"]
  ignore = ["E501"]

  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  ```
- [ ] Run Ruff on the project (should be clean):
  ```bash
  ruff check .
  ```

---

## Verification — Phase 01 Complete

Run all of these before moving to Phase 02:

- [ ] `python --version` → `Python 3.11.x`
- [ ] `which python` → points to `.venv/bin/python`
- [ ] `docker compose ps` → both `finsight_postgres` and `finsight_redis` show `healthy`
- [ ] `psql postgresql://finsight:finsight@localhost:5432/finsight -c "SELECT 1;"` → returns `1`
- [ ] `redis-cli ping` → `PONG`
- [ ] `python -c "from core.config import settings; print(settings.environment)"` → `development`
- [ ] `ruff check .` → no errors
- [ ] `git status` → `.env` is NOT listed (confirmed in .gitignore)

# Phase 10 — Deployment (Shareable Demo)

## Overview

This phase deploys FinSight so you can share a live URL with anyone. The target is a minimal, cost-effective setup that runs the full stack:
- FastAPI backend
- PostgreSQL database
- Redis + Celery worker
- MCP server (accessible for demos)

**Goal:** After this phase, you can say "here's the link" and someone can interact with your finance data via a live API or you can run a demo with Claude Desktop pointing at the deployed MCP server.

---

## Cost Breakdown — Complete Project

### Development (local) — Zero cost
| Component | Cost |
|---|---|
| Python, FastAPI, SQLAlchemy, etc. | Free / open source |
| Docker (Postgres + Redis) | Free |
| pyenv, venv, pip-compile | Free |

### Anthropic API — Pay as you go
Priced per million tokens (MTok) for `claude-sonnet-4-6` as of mid-2025:

| Call type | Est. tokens/call | Cost per call | Est. monthly (personal use) |
|---|---|---|---|
| CSV categorization (50 txns) | ~2K in + ~0.1K out | ~$0.006 | ~$0.06 (10 imports) |
| Subscription waste scoring (10 subs) | ~1K in + ~0.5K out | ~$0.004 | ~$0.02 |
| Scenario simulation | ~1K in + ~0.2K out | ~$0.003 | ~$0.03 (10 queries) |
| Health score digest | ~0.5K in + ~0.2K out | ~$0.002 | ~$0.008 (weekly) |
| **Total monthly estimate** | | | **< $0.20/month** |

> At personal use scale, Anthropic API cost is essentially zero. Even heavy use (100+ queries/month) stays under $2.

### Deployment hosting
| Platform | Free tier | Paid tier | Recommendation |
|---|---|---|---|
| **Railway** | $5 free credit/month | ~$5–15/month | ✅ Best for this project — one-click Postgres + Redis + app deploy |
| **Render** | Free (sleeps after 15 min) | $7/month starter | Good for demos; free tier is slow to wake |
| **Fly.io** | 3 shared VMs free | ~$2–5/month | Good if you want more control |
| **DigitalOcean App Platform** | No free tier | $12/month | Overkill for MVP |

**Recommendation: Railway** — native Postgres + Redis plugins, simple deploy from GitHub, $5 free credit covers light demo usage.

**Total monthly cost at demo scale: $0–$5** (Railway free credit usually covers it)

---

## Pros / Cons of Key Decisions

### Decision: Railway vs. Render for deployment

| | Railway | Render |
|---|---|---|
| **Pro** | Persistent free DB; doesn't sleep; good CLI; built-in Redis | Widely known; simpler free tier |
| **Con** | Free credit runs out; no always-free tier | Free web services sleep after 15 min — bad for demos |
| **Verdict** | ✅ Railway — doesn't sleep, native Postgres, better for live demos |

### Decision: Deploy MCP server alongside API vs. separate

| | Same service as API | Separate service |
|---|---|---|
| **Pro** | One deploy, one service | Independent scaling |
| **Con** | Can't use stdio transport over the internet — MCP server needs to be run locally or via tunnel | Extra complexity |
| **Verdict** | ✅ For demos: use `ngrok` tunnel to expose local MCP server. For full cloud deploy: expose MCP as HTTP SSE. Both approaches documented below. |

### Decision: Dockerfile vs. Railway's buildpack detection

| | Dockerfile | Buildpack (auto-detect) |
|---|---|---|
| **Pro** | Full control; reproducible | Zero config — Railway detects Python and builds automatically |
| **Con** | More to maintain | Less control over build steps |
| **Verdict** | ✅ Dockerfile — gives you Alembic migration step in the build process, which buildpacks can't easily handle |

---

## Checklist

### 1. Prepare the application for production

- [ ] Create `Dockerfile`:
  ```dockerfile
  FROM python:3.11-slim

  WORKDIR /app

  # Install system dependencies
  RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

  # Install Python dependencies
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  # Copy application code
  COPY . .

  # Run migrations then start the server
  CMD alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
  ```
- [ ] Create `.dockerignore`:
  ```
  .venv/
  .git/
  __pycache__/
  *.pyc
  .env
  .pytest_cache/
  htmlcov/
  .coverage
  docs/
  tests/
  *.egg-info/
  ```
- [ ] Build and test Docker image locally:
  ```bash
  docker build -t finsight:local .
  docker run --env-file .env -p 8000:8000 finsight:local
  curl http://localhost:8000/health
  ```

---

### 2. Add production environment config

- [ ] Update `core/config.py` to handle production settings:
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

      @property
      def is_production(self) -> bool:
          return self.environment == "production"
  ```
- [ ] Update `core/app.py` to disable debug logging in production:
  ```python
  engine = create_async_engine(
      settings.database_url,
      echo=not settings.is_production,  # no SQL logging in prod
      pool_pre_ping=True,
  )
  ```
- [ ] Ensure `python-dotenv` loads `.env` only in development (Railway sets env vars directly):
  ```python
  # Already handled by pydantic-settings env_file — it only reads the file if it exists
  ```

---

### 3. Deploy to Railway

- [ ] Install Railway CLI:
  ```bash
  brew install railway
  ```
- [ ] Login:
  ```bash
  railway login
  ```
- [ ] Initialize a new Railway project from your repo root:
  ```bash
  railway init
  # Follow prompts: create new project, name it "finsight"
  ```
- [ ] Add PostgreSQL plugin:
  ```bash
  railway add --plugin postgresql
  ```
- [ ] Add Redis plugin:
  ```bash
  railway add --plugin redis
  ```
- [ ] Set environment variables on Railway:
  ```bash
  railway variables set ANTHROPIC_API_KEY=your_key_here
  railway variables set ENVIRONMENT=production
  # DATABASE_URL and REDIS_URL are auto-injected by Railway plugins
  ```
- [ ] Deploy:
  ```bash
  railway up
  ```
- [ ] Get the deployment URL:
  ```bash
  railway open
  ```
- [ ] Test the deployed health endpoint:
  ```bash
  curl https://your-railway-url.up.railway.app/health
  # Expected: {"status":"ok","database":"connected"}
  ```

---

### 4. Deploy the Celery worker (Railway separate service)

The Celery worker needs to run as a separate process from the API.

- [ ] In Railway dashboard, create a new service in the same project
- [ ] Set the start command for the worker service:
  ```bash
  celery -A core.celery_app.celery_app worker --loglevel=info
  ```
- [ ] Set the same environment variables (Railway lets you share env vars across services)
- [ ] Verify the worker is running in Railway logs

---

### 5. Option A — Demo via ngrok (MCP + Claude Desktop → cloud DB)

This is the easiest demo path: run the MCP server locally but pointing at the deployed cloud database.

- [ ] Install ngrok:
  ```bash
  brew install ngrok
  ngrok authtoken your_ngrok_token  # from ngrok.com
  ```
- [ ] Update your local `.env` to point at the Railway database URL:
  ```bash
  # Get the Railway DB URL:
  railway variables get DATABASE_URL
  # Paste into local .env as DATABASE_URL
  ```
- [ ] Start the MCP server locally (it will connect to cloud DB):
  ```bash
  python -m mcp_server.server
  ```
- [ ] Claude Desktop already connects to your local MCP server — it now reads from the cloud DB
- [ ] For a web demo, expose the FastAPI server via ngrok:
  ```bash
  python main.py &
  ngrok http 8000
  # Share the ngrok URL — it proxies to your local FastAPI
  ```

---

### 6. Option B — Full cloud MCP server (HTTP/SSE transport)

For a fully cloud-hosted demo where MCP runs on Railway too:

- [ ] Add `sse-starlette` to `requirements.in`:
  ```
  sse-starlette>=1.6.0
  ```
- [ ] Create `mcp_server/http_server.py`:
  ```python
  import asyncio

  from mcp.server.sse import SseServerTransport
  from starlette.applications import Starlette
  from starlette.routing import Mount, Route

  from mcp_server.server import server


  def create_mcp_app() -> Starlette:
      sse = SseServerTransport("/messages/")

      async def handle_sse(request):
          async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
              await server.run(streams[0], streams[1], server.create_initialization_options())

      return Starlette(
          routes=[
              Route("/sse", endpoint=handle_sse),
              Mount("/messages/", app=sse.handle_post_message),
          ]
      )


  mcp_app = create_mcp_app()
  ```
- [ ] Deploy as a second Railway service with start command:
  ```bash
  uvicorn mcp_server.http_server:mcp_app --host 0.0.0.0 --port ${PORT:-8001}
  ```
- [ ] Update Claude Desktop config to use the SSE URL:
  ```json
  {
    "mcpServers": {
      "finsight-cloud": {
        "url": "https://your-mcp-railway-url.up.railway.app/sse"
      }
    }
  }
  ```

---

### 7. Verify deployed stack end-to-end

- [ ] API health check: `curl https://your-app.up.railway.app/health` → `{"status":"ok"}`
- [ ] Import CSV via Swagger UI at `https://your-app.up.railway.app/docs`
- [ ] Trigger health score: `POST https://your-app.up.railway.app/api/v1/health-score/generate`
- [ ] Claude Desktop queries work against cloud DB (via Option A or B above)

---

### 8. Sharing the demo

For a non-technical demo:
1. **Have Railway deployed** and DB pre-loaded with 3 months of (anonymized) transaction data
2. **Open Claude Desktop** — confirm MCP server is connected
3. Walk through these queries in order:
   - *"What did I spend the most on last month?"* → `get_spending`
   - *"What subscriptions am I wasting money on?"* → `audit_subscriptions`
   - *"If I cut food delivery by half, when can I save up for a Goa trip (₹40,000)?"* → `run_scenario`
   - *"What's my financial health score?"* → `get_health_score`

---

## Verification — Phase 10 Complete

- [ ] Railway deployment is live and health endpoint returns 200
- [ ] Celery worker is running on Railway (check logs)
- [ ] Swagger UI accessible at the deployed URL
- [ ] Claude Desktop demo (Options A or B) works end-to-end
- [ ] All 4 demo queries produce correct answers
- [ ] Total infra cost confirmed < $5/month (or within Railway free tier)

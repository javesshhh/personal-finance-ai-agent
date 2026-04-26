from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="FinSight",
        description="Personal Finance Intelligence Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    from api.health import router as health_router
    from api.scenarios import router as scenarios_router
    from api.sessions import router as sessions_router
    from api.subscriptions import router as subscriptions_router
    from api.transactions import router as transactions_router

    app.include_router(health_router)
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(transactions_router, prefix="/api/v1")
    app.include_router(subscriptions_router, prefix="/api/v1")
    app.include_router(scenarios_router, prefix="/api/v1")

    return app

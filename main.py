import uvicorn

from core.app import create_app
from core.config import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=not settings.is_production,
    )

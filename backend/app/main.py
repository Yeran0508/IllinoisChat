from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Campus RAG API with grounded answers, safety checks, and evaluation.",
)
app.include_router(health_router, prefix="/api/v1")

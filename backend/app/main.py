from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.retrieval import router as retrieval_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Campus RAG API with grounded answers, safety checks, and evaluation.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[value.strip() for value in settings.cors_origins.split(",") if value.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(retrieval_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(evaluations_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")

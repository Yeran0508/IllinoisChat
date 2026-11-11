from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from redis.exceptions import RedisError

from app.caching.semantic import CacheMetrics
from app.dependencies import get_cache_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def read_metrics(
    metrics: Annotated[CacheMetrics, Depends(get_cache_metrics)],
) -> dict:
    try:
        return {"semantic_cache": metrics.snapshot()}
    except RedisError as error:
        raise HTTPException(status_code=503, detail="Metrics storage is unavailable") from error

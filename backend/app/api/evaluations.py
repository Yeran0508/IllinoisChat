from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.dependencies import get_retrieval_service
from app.evaluation.runner import RetrievalEvaluator
from app.retrieval.service import RetrievalService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


class EvaluationResponse(BaseModel):
    dataset: str
    total_cases: int
    scored_cases: int
    recall_at_5: float
    ndcg_at_10: float
    latency_ms: dict[str, float]
    review_status_counts: dict[str, int]


@router.post("/run", response_model=EvaluationResponse)
def run_evaluation(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> EvaluationResponse:
    path = Path(get_settings().evaluation_dataset_path)
    try:
        summary = RetrievalEvaluator(retrieval).run(path)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return EvaluationResponse(**asdict(summary))

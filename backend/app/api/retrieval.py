import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.dependencies import get_retrieval_service
from app.retrieval.service import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class SearchRequest(BaseModel):
    course_code: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default_factory=lambda: get_settings().retrieval_top_k, ge=1, le=50)


class SearchResultResponse(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    source_name: str
    content: str
    page_number: int | None
    section_path: str | None
    score: float
    retrieval_metadata: dict[str, float | int | str]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]


@router.post("/search", response_model=SearchResponse)
def search_chunks(
    request: SearchRequest,
    service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> SearchResponse:
    try:
        results = service.search(
            course_code=request.course_code,
            query=request.query,
            top_k=request.top_k,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return SearchResponse(
        query=request.query,
        results=[SearchResultResponse(**asdict(result)) for result in results],
    )

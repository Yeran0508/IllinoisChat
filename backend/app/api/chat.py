import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_chat_service
from app.generation.models import ChatModelError
from app.generation.service import GroundedChatService

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    course_code: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=4000)


class AnswerSentenceResponse(BaseModel):
    text: str
    citation_ids: list[int]


class CitationResponse(BaseModel):
    citation_id: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    source_name: str
    page_number: int | None
    section_path: str | None
    evidence: str
    score: float


class ChatResponse(BaseModel):
    request_id: uuid.UUID
    status: str
    answer: str | None
    sentences: list[AnswerSentenceResponse]
    citations: list[CitationResponse]
    refusal_reason: str | None
    retrieved_chunk_ids: list[uuid.UUID]
    model_name: str
    latency_ms: int


@router.post("", response_model=ChatResponse)
def answer_question(
    request: ChatRequest,
    service: Annotated[GroundedChatService, Depends(get_chat_service)],
) -> ChatResponse:
    try:
        result = service.ask(course_code=request.course_code, query=request.query)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ChatModelError as error:
        raise HTTPException(status_code=503, detail="The answer model is unavailable") from error
    return ChatResponse(**asdict(result))

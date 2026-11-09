import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.db.models import ChatRequestLog


@dataclass(frozen=True, slots=True)
class ChatAuditEvent:
    request_id: uuid.UUID
    course_code: str
    query_sha256: str
    outcome: str
    refusal_reason: str | None
    model_name: str
    top_score: float | None
    latency_ms: int
    retrieved_chunk_ids: list[str]
    cited_chunk_ids: list[str]


class ChatAuditLogger(Protocol):
    def record(self, event: ChatAuditEvent) -> None: ...


class SqlAlchemyChatAuditLogger:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, event: ChatAuditEvent) -> None:
        self.session.add(
            ChatRequestLog(
                id=event.request_id,
                course_code=event.course_code,
                query_sha256=event.query_sha256,
                outcome=event.outcome,
                refusal_reason=event.refusal_reason,
                model_name=event.model_name,
                top_score=event.top_score,
                latency_ms=event.latency_ms,
                retrieved_chunk_ids=event.retrieved_chunk_ids,
                cited_chunk_ids=event.cited_chunk_ids,
            )
        )
        self.session.commit()

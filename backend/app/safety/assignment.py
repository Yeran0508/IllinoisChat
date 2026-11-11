import re
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Float, cast, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document, DocumentVersion
from app.retrieval.embeddings import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class AssignmentMatch:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    section_path: str | None
    score: float


class ProtectedAssignmentMatcher(Protocol):
    def match(self, *, course_code: str, query: str) -> AssignmentMatch | None: ...


class NoProtectedAssignmentMatcher:
    def match(self, *, course_code: str, query: str) -> AssignmentMatch | None:
        del course_code, query
        return None


class SqlAlchemyProtectedAssignmentMatcher:
    def __init__(
        self,
        session: Session,
        embedder: EmbeddingProvider,
        *,
        minimum_score: float,
    ) -> None:
        if not 0 <= minimum_score <= 1:
            raise ValueError("minimum_score must be between 0 and 1")
        self.session = session
        self.embedder = embedder
        self.minimum_score = minimum_score

    def match(self, *, course_code: str, query: str) -> AssignmentMatch | None:
        normalized = query.strip()
        if not normalized:
            raise ValueError("Query must not be blank")
        vector = self.embedder.embed_query(normalized)
        if len(vector) != self.embedder.dimension:
            raise ValueError("Embedding provider returned an unexpected vector dimension")

        distance = Chunk.embedding.cosine_distance(vector)
        rows = self.session.execute(
            select(Chunk, Document, cast(1 - distance, Float).label("score"))
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .join(Course, Document.course_id == Course.id)
            .where(
                Course.code == course_code,
                Document.is_protected.is_(True),
                DocumentVersion.status == "completed",
                Chunk.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(20)
        ).all()
        if not rows:
            return None
        for row in rows:
            identity = " ".join(
                value for value in (row.Document.title, row.Chunk.section_path) if value
            )
            if references_same_assignment(normalized, identity):
                return self._match(row)
        best = rows[0]
        if float(best.score) >= self.minimum_score and requests_solution(normalized):
            return self._match(best)
        return None

    @staticmethod
    def _match(row) -> AssignmentMatch:
        return AssignmentMatch(
            chunk_id=row.Chunk.id,
            document_id=row.Document.id,
            title=row.Document.title,
            section_path=row.Chunk.section_path,
            score=float(row.score),
        )


def build_bounded_hint(match: AssignmentMatch, hint_level: int) -> str:
    location = match.section_path or match.title
    if hint_level == 1:
        return f"Review the concepts in ‘{location}’ and identify the rule the question tests."
    if hint_level == 2:
        return (
            f"Start from ‘{location}’: list the given information, the required result, and the "
            "single course concept connecting them."
        )
    if hint_level == 3:
        return (
            f"Use ‘{location}’ as your guide. First write the relevant definition or invariant, "
            "then apply it to one small part of the problem and check that step before continuing."
        )
    raise ValueError("hint_level must be between 1 and 3")


NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
}


def _canonical_identity(text: str) -> tuple[str | None, str | None]:
    normalized = text.casefold()
    normalized = re.sub(r"\bhw\b", "assignment ", normalized)
    normalized = re.sub(r"\bhw(?=\d)", "assignment ", normalized)
    normalized = re.sub(r"\bhomework\b", "assignment", normalized)
    normalized = re.sub(r"\bproblem\b|\bq(?=\s*\d)", "question ", normalized)
    for word, number in NUMBER_WORDS.items():
        normalized = re.sub(rf"\b{word}\b", number, normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    assignment = re.search(r"\bassignment\s+(\d+)\b", normalized)
    question = re.search(r"\bquestion\s+(\d+)\b", normalized)
    return (
        assignment.group(1) if assignment else None,
        question.group(1) if question else None,
    )


def references_same_assignment(query: str, protected_identity: str) -> bool:
    query_assignment, query_question = _canonical_identity(query)
    source_assignment, source_question = _canonical_identity(protected_identity)
    return (
        query_assignment is not None
        and query_question is not None
        and query_assignment == source_assignment
        and query_question == source_question
    )


def requests_solution(query: str) -> bool:
    normalized = query.casefold()
    markers = (
        "final answer",
        "complete solution",
        "complete implementation",
        "solve ",
        "write the code",
        "provide code",
        "so i can submit",
    )
    return any(marker in normalized for marker in markers)

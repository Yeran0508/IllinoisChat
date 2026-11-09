import uuid
from dataclasses import dataclass

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document, DocumentVersion
from app.retrieval.embeddings import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    title: str
    source_name: str
    content: str
    page_number: int | None
    section_path: str | None
    score: float


class VectorRetrievalService:
    def __init__(
        self,
        session: Session,
        embedder: EmbeddingProvider,
        *,
        ef_search: int = 64,
    ) -> None:
        if ef_search <= 0:
            raise ValueError("ef_search must be positive")
        self.session = session
        self.embedder = embedder
        self.ef_search = ef_search

    def search(self, *, course_code: str, query: str, top_k: int) -> list[RetrievalResult]:
        query = query.strip()
        if not query:
            raise ValueError("Query must not be blank")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50")

        vector = self.embedder.embed_query(query)
        if len(vector) != self.embedder.dimension:
            raise ValueError("Embedding provider returned an unexpected vector dimension")

        self.session.execute(select(func.set_config("hnsw.ef_search", str(self.ef_search), True)))
        distance = Chunk.embedding.cosine_distance(vector)
        rows = self.session.execute(
            select(
                Chunk,
                Document,
                DocumentVersion,
                cast(1 - distance, Float).label("score"),
            )
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .join(Course, Document.course_id == Course.id)
            .where(
                Course.code == course_code,
                DocumentVersion.status == "completed",
                Chunk.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(top_k)
        ).all()

        return [
            RetrievalResult(
                chunk_id=chunk.id,
                document_id=document.id,
                version_id=version.id,
                title=document.title,
                source_name=document.source_name,
                content=chunk.content,
                page_number=chunk.page_number,
                section_path=chunk.section_path,
                score=float(score),
            )
            for chunk, document, version, score in rows
        ]

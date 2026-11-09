import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Chunk, Course, Document, DocumentVersion
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.parsers import SUPPORTED_MEDIA_TYPES, parse_document
from app.ingestion.storage import LocalDocumentStorage
from app.retrieval.embeddings import EmbeddingProvider


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    document_id: uuid.UUID
    version_id: uuid.UUID
    status: str
    reused: bool


class DocumentNotFoundError(LookupError):
    pass


class DocumentIngestionService:
    def __init__(
        self,
        session: Session,
        storage: LocalDocumentStorage,
        embedder: EmbeddingProvider,
        chunker: StructureAwareChunker,
        max_upload_bytes: int,
    ) -> None:
        self.session = session
        self.storage = storage
        self.embedder = embedder
        self.chunker = chunker
        self.max_upload_bytes = max_upload_bytes

    def register(
        self,
        *,
        course_code: str,
        course_name: str,
        title: str,
        source_name: str,
        media_type: str,
        content: bytes,
    ) -> RegistrationResult:
        course_code = course_code.strip()
        course_name = course_name.strip()
        title = title.strip()
        source_name = source_name.strip()
        if not all((course_code, course_name, title, source_name)):
            raise ValueError("Course code, course name, title, and source name are required")
        if media_type not in SUPPORTED_MEDIA_TYPES:
            raise ValueError(f"Unsupported media type: {media_type}")
        if not content:
            raise ValueError("Uploaded file is empty")
        if len(content) > self.max_upload_bytes:
            raise ValueError(f"Uploaded file exceeds {self.max_upload_bytes} bytes")

        digest = hashlib.sha256(content).hexdigest()
        course = self.session.scalar(select(Course).where(Course.code == course_code))
        if course is None:
            course = Course(id=uuid.uuid4(), code=course_code, name=course_name)
            self.session.add(course)
            self.session.flush()

        document = self.session.scalar(
            select(Document).where(
                Document.course_id == course.id,
                Document.source_name == source_name,
            )
        )
        if document is None:
            document = Document(
                id=uuid.uuid4(),
                course_id=course.id,
                title=title,
                source_name=source_name,
            )
            self.session.add(document)
            self.session.flush()
        else:
            document.title = title

        existing = self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.content_sha256 == digest,
            )
        )
        if existing is not None:
            self.session.commit()
            return RegistrationResult(document.id, existing.id, existing.status, True)

        version_id = uuid.uuid4()
        storage_key: str | None = None
        try:
            storage_key = self.storage.put(version_id, source_name, content)
            version = DocumentVersion(
                id=version_id,
                document_id=document.id,
                content_sha256=digest,
                media_type=media_type,
                byte_size=len(content),
                storage_key=storage_key,
                status="pending",
            )
            self.session.add(version)
            self.session.commit()
            return RegistrationResult(document.id, version.id, version.status, False)
        except Exception:
            self.session.rollback()
            if storage_key is not None:
                self.storage.delete(storage_key)
            raise

    def ingest(self, version_id: uuid.UUID) -> DocumentVersion:
        version = self.session.get(DocumentVersion, version_id)
        if version is None:
            raise DocumentNotFoundError(f"Document version {version_id} was not found")
        if version.status == "completed":
            return version

        version.status = "processing"
        version.error_message = None
        self.session.commit()

        try:
            content = self.storage.read(version.storage_key)
            parsed = parse_document(content, version.media_type)
            chunk_values = self.chunker.chunk(parsed)
            if not chunk_values:
                raise ValueError("Document produced no chunks")

            embeddings = self.embedder.embed_documents([chunk.content for chunk in chunk_values])
            if len(embeddings) != len(chunk_values):
                raise ValueError("Embedding provider returned an unexpected vector count")
            if any(len(vector) != self.embedder.dimension for vector in embeddings):
                raise ValueError("Embedding provider returned an unexpected vector dimension")

            self.session.execute(delete(Chunk).where(Chunk.document_version_id == version.id))
            for chunk, embedding in zip(chunk_values, embeddings, strict=True):
                self.session.add(
                    Chunk(
                        id=uuid.uuid4(),
                        document_version_id=version.id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        content_sha256=chunk.content_sha256,
                        char_count=chunk.char_count,
                        page_number=chunk.page_number,
                        section_path=chunk.section_path,
                        block_type=chunk.block_type,
                        chunk_metadata=chunk.metadata,
                        embedding=embedding,
                    )
                )

            version.status = "completed"
            version.embedding_model = self.embedder.model_name
            version.completed_at = datetime.now(UTC)
            self.session.commit()
            self.session.refresh(version)
            return version
        except Exception as error:
            self.session.rollback()
            failed = self.session.get(DocumentVersion, version_id)
            if failed is not None:
                failed.status = "failed"
                failed.error_message = str(error)[:2000]
                self.session.commit()
            raise

    def get_document(self, document_id: uuid.UUID) -> Document:
        document = self.session.scalar(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.versions))
        )
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} was not found")
        return document

    def delete_document(self, document_id: uuid.UUID) -> None:
        document = self.get_document(document_id)
        storage_keys = [version.storage_key for version in document.versions]
        self.session.delete(document)
        self.session.commit()
        for key in storage_keys:
            self.storage.delete(key)

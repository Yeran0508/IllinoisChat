import argparse
import json
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import Chunk, Course, Document, DocumentVersion
from app.db.session import SessionLocal
from app.evaluation.safety import SafetyEvaluator, contains_solution_leakage, load_safety_dataset
from app.generation.service import GroundedChatService
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.service import DocumentIngestionService
from app.ingestion.storage import LocalDocumentStorage
from app.retrieval.embeddings import FastEmbedBgeProvider
from app.retrieval.lexical import OpenSearchBM25Index
from app.retrieval.service import VectorRetrievalService
from app.safety.assignment import SqlAlchemyProtectedAssignmentMatcher


class StaticSafetyBaselineModel:
    model_name = "deterministic-safety-baseline-model"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **_kwargs) -> str:
        self.calls += 1
        return (
            '{"sufficient":true,"sentences":['
            '{"text":"This is a permitted conceptual explanation.","citation_ids":[1]}]}'
        )


class NoOpAudit:
    def record(self, _event) -> None:
        return None


class AllowAllSupport:
    def validate(self, *, sentences, cited_sources):
        del cited_sources
        return [True] * len(sentences)


@dataclass(frozen=True, slots=True)
class CaseResult:
    id: str
    expected_protected: bool
    expected_behavior: str
    actual_status: str
    behavior_compliant: bool
    protection_bypassed: bool
    solution_leakage: bool
    protected_match_score: float | None
    answer: str | None


def _replace_corpus(ingestion, session, path: Path, *, protected: bool) -> None:
    course = session.scalar(select(Course).where(Course.code == "CS-RAG"))
    if course is not None:
        existing = session.scalar(
            select(Document).where(
                Document.course_id == course.id,
                Document.source_name == path.name,
            )
        )
        if existing is not None:
            ingestion.delete_document(existing.id)
    registered = ingestion.register(
        course_code="CS-RAG",
        course_name="Synthetic RAG Safety",
        title=path.stem.replace("-", " ").title(),
        source_name=path.name,
        media_type="text/markdown",
        content=path.read_bytes(),
        is_protected=protected,
    )
    ingestion.ingest(registered.version_id)


def run(output: Path) -> dict:
    settings = get_settings()
    ordinary_corpus = Path("data/sample/m2-retrieval-notes.md")
    protected_corpus = Path("data/sample/m3-protected-homework.md")
    dataset_path = Path("data/evaluation/m3-safety-v1.jsonl")
    embedder = FastEmbedBgeProvider(
        model_name=settings.embedding_model,
        cache_dir=str(settings.embedding_cache_path),
    )
    lexical = OpenSearchBM25Index(
        base_url=f"http://{settings.opensearch_host}:{settings.opensearch_port}",
        index_name=settings.opensearch_index,
        timeout_seconds=settings.opensearch_timeout_seconds,
    )
    with SessionLocal() as session:
        ingestion = DocumentIngestionService(
            session=session,
            storage=LocalDocumentStorage(settings.document_storage_path),
            embedder=embedder,
            chunker=StructureAwareChunker(
                settings.chunk_max_characters,
                settings.chunk_overlap_characters,
            ),
            max_upload_bytes=settings.max_upload_bytes,
            lexical_index=lexical,
        )
        _replace_corpus(ingestion, session, ordinary_corpus, protected=False)
        _replace_corpus(ingestion, session, protected_corpus, protected=True)

        model = StaticSafetyBaselineModel()
        chat = GroundedChatService(
            retrieval=VectorRetrievalService(session, embedder, ef_search=64),
            model=model,
            audit=NoOpAudit(),
            top_k=settings.retrieval_top_k,
            minimum_score=0.0,
            assignment_matcher=SqlAlchemyProtectedAssignmentMatcher(
                session,
                embedder,
                minimum_score=settings.protected_assignment_min_score,
            ),
            sentence_support=AllowAllSupport(),
            hint_level=settings.homework_hint_level,
        )
        summary = SafetyEvaluator(chat).run(dataset_path)
        case_results: list[CaseResult] = []
        for case in load_safety_dataset(dataset_path):
            result = chat.ask(course_code=case.course_code, query=case.query)
            protected_behavior = case.expected_behavior != "allow_explanation"
            compliant = (
                result.status == "homework_hint" and bool(result.answer)
                if protected_behavior
                else result.status == "answered"
            )
            case_results.append(
                CaseResult(
                    id=case.id,
                    expected_protected=case.expected_protected,
                    expected_behavior=case.expected_behavior,
                    actual_status=result.status,
                    behavior_compliant=compliant,
                    protection_bypassed=case.expected_protected
                    and result.status != "homework_hint",
                    solution_leakage=case.expected_protected
                    and contains_solution_leakage(result.answer),
                    protected_match_score=result.protected_match_score,
                    answer=result.answer,
                )
            )
        ordinary_chunk_count = session.scalar(
            select(func.count())
            .select_from(Chunk)
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Document.is_protected.is_(False))
        )
        protected_chunk_count = session.scalar(
            select(func.count())
            .select_from(Chunk)
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Document.is_protected.is_(True))
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": dataset_path.name,
        "dataset_review_status": "human_reviewed",
        "ordinary_corpus": ordinary_corpus.name,
        "protected_corpus": protected_corpus.name,
        "ordinary_chunk_count": ordinary_chunk_count,
        "protected_chunk_count": protected_chunk_count,
        "python": sys.version,
        "platform": platform.platform(),
        "embedding_model": settings.embedding_model,
        "protected_assignment_min_score": settings.protected_assignment_min_score,
        "detector": "assignment/question identity match OR risk-intent-gated semantic match",
        "hint_level": settings.homework_hint_level,
        "answer_model": model.model_name,
        "summary": asdict(summary),
        "cases": [asdict(result) for result in case_results],
        "limitations": [
            "Leakage detection uses transparent code/solution markers, not semantic equivalence.",
            "Benign answer quality is out of scope; a deterministic model isolates safety routing.",
            "The same small human-reviewed dataset is used for this baseline, not a held-out set.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), indent=2))


if __name__ == "__main__":
    main()

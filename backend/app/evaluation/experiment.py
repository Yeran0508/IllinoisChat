import argparse
import json
import platform
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Course, Document
from app.db.session import SessionLocal
from app.evaluation.runner import RetrievalEvaluator
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.service import DocumentIngestionService
from app.ingestion.storage import LocalDocumentStorage
from app.retrieval.embeddings import FastEmbedBgeProvider
from app.retrieval.hybrid import HybridRetrievalService
from app.retrieval.lexical import OpenSearchBM25Index
from app.retrieval.reranking import FastEmbedCrossEncoderReranker
from app.retrieval.service import VectorRetrievalService


def run(output: Path, repetitions: int) -> dict:
    settings = get_settings()
    corpus_path = Path("data/sample/m2-retrieval-notes.md")
    dataset_path = Path(settings.evaluation_dataset_path)
    embedder = FastEmbedBgeProvider(
        model_name=settings.embedding_model,
        cache_dir=str(settings.embedding_cache_path),
    )
    lexical = OpenSearchBM25Index(
        base_url=f"http://{settings.opensearch_host}:{settings.opensearch_port}",
        index_name=settings.opensearch_index,
        timeout_seconds=settings.opensearch_timeout_seconds,
    )
    reranker = FastEmbedCrossEncoderReranker(
        settings.reranker_model, str(settings.embedding_cache_path)
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
        course = session.scalar(select(Course).where(Course.code == "CS-RAG"))
        if course is not None:
            existing = session.scalar(
                select(Document).where(
                    Document.course_id == course.id,
                    Document.source_name == corpus_path.name,
                )
            )
            if existing is not None:
                ingestion.delete_document(existing.id)
        registered = ingestion.register(
            course_code="CS-RAG",
            course_name="Synthetic RAG Retrieval",
            title="M2 Retrieval Notes",
            source_name=corpus_path.name,
            media_type="text/markdown",
            content=corpus_path.read_bytes(),
        )
        ingestion.ingest(registered.version_id)

        vector64 = VectorRetrievalService(session, embedder, ef_search=64)
        hybrid = HybridRetrievalService(
            vector=vector64,
            lexical=lexical,
            reranker=reranker,
            candidate_k=settings.retrieval_candidate_k,
            rrf_rank_constant=settings.rrf_rank_constant,
        )
        pipelines = {
            "vector_ef64": vector64,
            "bm25": lexical,
            "hybrid_reranked": hybrid,
        }
        results = {
            name: asdict(RetrievalEvaluator(service).run(dataset_path, repetitions))
            for name, service in pipelines.items()
        }
        hnsw = {
            str(ef): asdict(
                RetrievalEvaluator(VectorRetrievalService(session, embedder, ef_search=ef)).run(
                    dataset_path, repetitions
                )
            )
            for ef in (16, 64, 256)
        }
        chunk_count = len(vector64.search(course_code="CS-RAG", query="retrieval", top_k=50))

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": dataset_path.name,
        "dataset_review_status": "pending_human_review",
        "corpus": corpus_path.name,
        "chunk_count": chunk_count,
        "repetitions": repetitions,
        "python": sys.version,
        "platform": platform.platform(),
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "candidate_k": settings.retrieval_candidate_k,
        "rrf_rank_constant": settings.rrf_rank_constant,
        "pipelines": results,
        "hnsw": hnsw,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.repetitions), indent=2))


if __name__ == "__main__":
    main()

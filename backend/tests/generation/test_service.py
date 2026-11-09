import uuid
from dataclasses import dataclass, field

import pytest
from app.generation.audit import ChatAuditEvent
from app.generation.models import ChatModelError
from app.generation.service import GroundedChatService
from app.retrieval.service import RetrievalResult


def evidence(score: float = 0.91) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.UUID(int=1),
        document_id=uuid.UUID(int=2),
        version_id=uuid.UUID(int=3),
        title="Vector Notes",
        source_name="notes.md",
        content="HNSW trades exactness for lower query latency.",
        page_number=None,
        section_path="Indexes > HNSW",
        score=score,
    )


@dataclass
class FakeRetrieval:
    results: list[RetrievalResult]

    def search(self, **_kwargs) -> list[RetrievalResult]:
        return self.results


@dataclass
class FakeModel:
    response: str = ""
    error: bool = False
    model_name: str = "test-model"
    calls: int = 0
    prompt: str = ""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        self.prompt = system_prompt + user_prompt
        if self.error:
            raise ChatModelError("offline")
        return self.response


@dataclass
class FakeAudit:
    events: list[ChatAuditEvent] = field(default_factory=list)

    def record(self, event: ChatAuditEvent) -> None:
        self.events.append(event)


def service(results, response="", *, error=False):
    model = FakeModel(response=response, error=error)
    audit = FakeAudit()
    value = GroundedChatService(
        retrieval=FakeRetrieval(results),
        model=model,
        audit=audit,
        top_k=5,
        minimum_score=0.35,
    )
    return value, model, audit


def test_answer_has_sentence_level_citations_and_hash_only_audit() -> None:
    chat, model, audit = service(
        [evidence()],
        '{"sufficient":true,"sentences":['
        '{"text":"HNSW lowers query latency.","citation_ids":[1,1]}]}',
    )

    result = chat.ask(course_code="CS411", query="What does HNSW trade off?")

    assert result.status == "answered"
    assert result.answer == "HNSW lowers query latency."
    assert result.sentences[0].citation_ids == [1]
    assert result.citations[0].section_path == "Indexes > HNSW"
    assert '<source id="1"' in model.prompt
    assert audit.events[0].outcome == "answered"
    assert audit.events[0].query_sha256 != "What does HNSW trade off?"
    assert len(audit.events[0].query_sha256) == 64


@pytest.mark.parametrize(
    ("results", "reason"),
    [([], "no_evidence"), ([evidence(0.2)], "low_retrieval_score")],
)
def test_retrieval_gate_refuses_without_calling_model(results, reason) -> None:
    chat, model, audit = service(results)

    result = chat.ask(course_code="CS411", query="unsupported")

    assert result.status == "insufficient_evidence"
    assert result.refusal_reason == reason
    assert model.calls == 0
    assert audit.events[0].outcome == "refused"


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ('{"sufficient":false,"sentences":[]}', "model_insufficient_evidence"),
        ("not json", "invalid_model_output"),
        (
            '{"sufficient":true,"sentences":[{"text":"Unsupported.","citation_ids":[2]}]}',
            "invalid_citation",
        ),
        ('{"sufficient":true,"sentences":[]}', "invalid_model_output"),
    ],
)
def test_model_sufficiency_and_output_validation_refuse(response, reason) -> None:
    chat, _model, audit = service([evidence()], response)

    result = chat.ask(course_code="CS411", query="question")

    assert result.refusal_reason == reason
    assert not result.citations
    assert audit.events[0].refusal_reason == reason


def test_model_error_is_audited_and_re_raised() -> None:
    chat, _model, audit = service([evidence()], error=True)

    with pytest.raises(ChatModelError, match="offline"):
        chat.ask(course_code="CS411", query="question")

    assert audit.events[0].outcome == "model_error"


def test_blank_query_is_rejected() -> None:
    chat, _model, audit = service([])

    with pytest.raises(ValueError, match="blank"):
        chat.ask(course_code="CS411", query="  ")

    assert audit.events == []

import pytest
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.types import ParsedBlock, ParsedDocument


def test_chunker_preserves_metadata_and_stable_indexes() -> None:
    document = ParsedDocument(
        media_type="text/markdown",
        blocks=(
            ParsedBlock(
                content="Vector retrieval explanation.",
                block_type="paragraph",
                page_number=3,
                section_path=("Retrieval", "Vector"),
                metadata={"source_format": "markdown"},
            ),
        ),
    )

    chunks = StructureAwareChunker(max_characters=100, overlap_characters=10).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].page_number == 3
    assert chunks[0].section_path == "Retrieval > Vector"
    assert chunks[0].char_count == len(chunks[0].content)
    assert len(chunks[0].content_sha256) == 64


def test_long_code_block_splits_on_lines_with_overlap() -> None:
    content = "\n".join(f"line_{number} = {number}" for number in range(20))
    document = ParsedDocument(
        media_type="text/markdown",
        blocks=(ParsedBlock(content=content, block_type="code"),),
    )

    chunks = StructureAwareChunker(max_characters=80, overlap_characters=15).chunk(document)

    assert len(chunks) > 1
    assert all(chunk.block_type == "code" for chunk in chunks)
    assert all(chunk.char_count <= 80 for chunk in chunks)
    assert all(chunk.content.startswith("line_") for chunk in chunks)


def test_long_paragraph_uses_space_boundaries() -> None:
    content = " ".join(f"word{number}" for number in range(40))
    document = ParsedDocument(
        media_type="text/plain",
        blocks=(ParsedBlock(content=content, block_type="paragraph"),),
    )

    chunks = StructureAwareChunker(max_characters=70, overlap_characters=10).chunk(document)

    assert len(chunks) > 1
    assert all(chunk.char_count <= 70 for chunk in chunks)


def test_empty_block_is_ignored() -> None:
    document = ParsedDocument(
        media_type="text/plain",
        blocks=(ParsedBlock(content="  ", block_type="paragraph"),),
    )

    assert StructureAwareChunker().chunk(document) == []


@pytest.mark.parametrize(
    ("max_characters", "overlap_characters"),
    [(0, 0), (100, -1), (100, 100), (100, 101)],
)
def test_invalid_chunk_configuration_is_rejected(
    max_characters: int, overlap_characters: int
) -> None:
    with pytest.raises(ValueError):
        StructureAwareChunker(max_characters, overlap_characters)

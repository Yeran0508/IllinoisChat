import io

import pytest
from app.ingestion.parsers import EmptyDocumentError, parse_document
from pypdf import PdfWriter


def test_markdown_parser_preserves_heading_hierarchy_and_code_block() -> None:
    content = b"""# Retrieval

Vector search finds semantic matches.

## Example

```python
result = search(query)
print(result)
```
"""

    document = parse_document(content, "text/markdown")

    assert [block.block_type for block in document.blocks] == [
        "heading",
        "paragraph",
        "heading",
        "code",
    ]
    assert document.blocks[1].section_path == ("Retrieval",)
    assert document.blocks[3].section_path == ("Retrieval", "Example")
    assert document.blocks[3].metadata["language"] == "python"
    assert "print(result)" in document.blocks[3].content


def test_plain_text_parser_ignores_empty_paragraphs() -> None:
    document = parse_document(b"First paragraph.\n\n\nSecond paragraph.", "text/plain")

    assert [block.content for block in document.blocks] == [
        "First paragraph.",
        "Second paragraph.",
    ]


def test_empty_document_is_rejected() -> None:
    with pytest.raises(EmptyDocumentError, match="no extractable text"):
        parse_document(b"  \n\n", "text/plain")


def test_non_utf8_text_is_rejected() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        parse_document(b"\xff\xfe", "text/plain")


def test_unclosed_markdown_code_fence_is_rejected() -> None:
    with pytest.raises(ValueError, match="unclosed fenced code block"):
        parse_document(b"```python\nprint('hello')", "text/markdown")


def test_unsupported_media_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported media type"):
        parse_document(b"content", "application/json")


def test_blank_pdf_is_rejected_after_page_extraction() -> None:
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(stream)

    with pytest.raises(EmptyDocumentError, match="no extractable text"):
        parse_document(stream.getvalue(), "application/pdf")


def test_markdown_flushes_paragraph_before_code_fence() -> None:
    content = b"Intro paragraph.\n```sql\nSELECT 1;\n```"

    document = parse_document(content, "text/markdown")

    assert [block.block_type for block in document.blocks] == ["paragraph", "code"]
    assert document.blocks[1].metadata["language"] == "sql"

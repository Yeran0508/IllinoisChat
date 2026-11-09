import io
import re
from collections.abc import Iterable

from pypdf import PdfReader

from app.ingestion.types import ParsedBlock, ParsedDocument

SUPPORTED_MEDIA_TYPES = {
    "application/pdf",
    "text/markdown",
    "text/plain",
}


class UnsupportedDocumentTypeError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


def parse_document(content: bytes, media_type: str) -> ParsedDocument:
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise UnsupportedDocumentTypeError(f"Unsupported media type: {media_type}")

    if media_type == "application/pdf":
        blocks = tuple(_parse_pdf(content))
    else:
        text = _decode_text(content)
        blocks = tuple(
            _parse_markdown(text) if media_type == "text/markdown" else _parse_text(text)
        )

    if not blocks:
        raise EmptyDocumentError("The document contains no extractable text")

    return ParsedDocument(blocks=blocks, media_type=media_type)


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Text documents must use UTF-8 encoding") from error


def _parse_pdf(content: bytes) -> Iterable[ParsedBlock]:
    reader = PdfReader(io.BytesIO(content))
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for paragraph in _paragraphs(text):
            yield ParsedBlock(
                content=paragraph,
                block_type="paragraph",
                page_number=page_number,
                metadata={"source_format": "pdf"},
            )


def _parse_text(text: str) -> Iterable[ParsedBlock]:
    for paragraph in _paragraphs(text):
        yield ParsedBlock(
            content=paragraph,
            block_type="paragraph",
            metadata={"source_format": "text"},
        )


def _parse_markdown(text: str) -> Iterable[ParsedBlock]:
    headings: list[str] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code = False
    code_language = ""

    def flush_paragraph() -> ParsedBlock | None:
        if not paragraph_lines:
            return None
        content = "\n".join(paragraph_lines).strip()
        paragraph_lines.clear()
        if not content:
            return None
        return ParsedBlock(
            content=content,
            block_type="paragraph",
            section_path=tuple(headings),
            metadata={"source_format": "markdown"},
        )

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        fence_match = re.match(r"^\s*```\s*([^`]*)$", line)
        if fence_match:
            if in_code:
                yield ParsedBlock(
                    content="\n".join(code_lines).strip("\n"),
                    block_type="code",
                    section_path=tuple(headings),
                    metadata={"source_format": "markdown", "language": code_language},
                )
                code_lines.clear()
                code_language = ""
                in_code = False
            else:
                paragraph = flush_paragraph()
                if paragraph:
                    yield paragraph
                in_code = True
                code_language = fence_match.group(1).strip()
            continue

        if in_code:
            code_lines.append(raw_line)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            paragraph = flush_paragraph()
            if paragraph:
                yield paragraph
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip().rstrip("#").strip()
            headings[level - 1 :] = [title]
            yield ParsedBlock(
                content=title,
                block_type="heading",
                section_path=tuple(headings),
                metadata={"source_format": "markdown", "heading_level": level},
            )
        elif not line.strip():
            paragraph = flush_paragraph()
            if paragraph:
                yield paragraph
        else:
            paragraph_lines.append(line)

    if in_code:
        raise ValueError("Markdown contains an unclosed fenced code block")
    paragraph = flush_paragraph()
    if paragraph:
        yield paragraph


def _paragraphs(text: str) -> Iterable[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for value in re.split(r"\n\s*\n", normalized):
        paragraph = "\n".join(line.rstrip() for line in value.splitlines()).strip()
        if paragraph:
            yield paragraph

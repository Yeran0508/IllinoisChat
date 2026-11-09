from dataclasses import dataclass, field
from typing import Literal

BlockType = Literal["heading", "paragraph", "code"]


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    content: str
    block_type: BlockType
    page_number: int | None = None
    section_path: tuple[str, ...] = ()
    metadata: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    blocks: tuple[ParsedBlock, ...]
    media_type: str


@dataclass(frozen=True, slots=True)
class ChunkData:
    index: int
    content: str
    content_sha256: str
    char_count: int
    block_type: BlockType
    page_number: int | None
    section_path: str | None
    metadata: dict[str, str | int | bool]

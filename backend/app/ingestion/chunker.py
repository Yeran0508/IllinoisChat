import hashlib

from app.ingestion.types import ChunkData, ParsedBlock, ParsedDocument


class StructureAwareChunker:
    def __init__(self, max_characters: int = 1200, overlap_characters: int = 150) -> None:
        if max_characters <= 0:
            raise ValueError("max_characters must be positive")
        if overlap_characters < 0 or overlap_characters >= max_characters:
            raise ValueError("overlap_characters must be between 0 and max_characters - 1")
        self.max_characters = max_characters
        self.overlap_characters = overlap_characters

    def chunk(self, document: ParsedDocument) -> list[ChunkData]:
        chunks: list[ChunkData] = []
        for block in document.blocks:
            for content in self._split_block(block):
                chunks.append(self._to_chunk(len(chunks), block, content))
        return chunks

    def _split_block(self, block: ParsedBlock) -> list[str]:
        content = block.content.strip()
        if not content:
            return []
        if len(content) <= self.max_characters:
            return [content]

        if block.block_type == "code":
            return self._sliding_windows(content, prefer_newline=True)
        return self._sliding_windows(content, prefer_newline=False)

    def _sliding_windows(self, content: str, *, prefer_newline: bool) -> list[str]:
        values: list[str] = []
        start = 0
        while start < len(content):
            limit = min(start + self.max_characters, len(content))
            end = limit
            if limit < len(content):
                search_start = start + max(1, self.max_characters // 2)
                preferred = content.rfind("\n" if prefer_newline else " ", search_start, limit)
                if preferred > start:
                    end = preferred
            value = content[start:end].strip()
            if value:
                values.append(value)
            if end >= len(content):
                break
            next_start = end - self.overlap_characters
            if prefer_newline and self.overlap_characters:
                line_start = content.rfind("\n", start, next_start)
                if line_start > start:
                    next_start = line_start + 1
            start = next_start if next_start > start else end
        return values

    @staticmethod
    def _to_chunk(index: int, block: ParsedBlock, content: str) -> ChunkData:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return ChunkData(
            index=index,
            content=content,
            content_sha256=digest,
            char_count=len(content),
            block_type=block.block_type,
            page_number=block.page_number,
            section_path=" > ".join(block.section_path) or None,
            metadata=dict(block.metadata),
        )

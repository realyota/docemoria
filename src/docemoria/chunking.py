from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .document_loading import SourceDocument


class ChunkingError(ValueError):
    """Raised when loaded documents cannot be chunked."""


@dataclass(slots=True)
class DocumentChunk:
    source_id: str
    absolute_path: Path
    repo_relative_path: str
    file_type: str
    document_index: int
    chunk_index: int
    start_char: int
    end_char: int
    content: str

    @property
    def character_count(self) -> int:
        return len(self.content)


SUPPORTED_CHUNKING_STRATEGIES = {"fixed-windows", "markdown-sections"}
_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+.*$")
_FENCE_RE = re.compile(r"^[ \t]*```")


@dataclass(slots=True)
class _SectionSpan:
    start_char: int
    end_char: int


def _validate_chunking_inputs(*, max_chars: int, overlap_chars: int) -> None:
    if max_chars <= 0:
        raise ChunkingError("chunking.max_chars must be greater than zero")
    if overlap_chars < 0:
        raise ChunkingError("chunking.overlap_chars must be zero or greater")
    if overlap_chars >= max_chars:
        raise ChunkingError("chunking.overlap_chars must be smaller than chunking.max_chars")


def _normalize_strategy(strategy: str) -> str:
    normalized = strategy.strip().lower()
    if normalized not in SUPPORTED_CHUNKING_STRATEGIES:
        supported = ", ".join(sorted(SUPPORTED_CHUNKING_STRATEGIES))
        raise ChunkingError(f"Unsupported chunking.strategy '{strategy}'. Supported values: {supported}")
    return normalized


def _build_chunk(
    document: SourceDocument,
    *,
    document_index: int,
    chunk_index: int,
    start_char: int,
    end_char: int,
) -> DocumentChunk:
    return DocumentChunk(
        source_id=document.source_id,
        absolute_path=document.absolute_path,
        repo_relative_path=document.repo_relative_path,
        file_type=document.file_type,
        document_index=document_index,
        chunk_index=chunk_index,
        start_char=start_char,
        end_char=end_char,
        content=document.content[start_char:end_char],
    )


def _fixed_window_spans(*, content_length: int, max_chars: int, overlap_chars: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start_char = 0

    while start_char < content_length:
        end_char = min(start_char + max_chars, content_length)
        spans.append((start_char, end_char))
        if end_char == content_length:
            break
        start_char = end_char - overlap_chars

    return spans


def _chunk_document_fixed_windows(
    document: SourceDocument,
    *,
    max_chars: int,
    overlap_chars: int,
    document_index: int,
    chunk_index_offset: int = 0,
    start_char_offset: int = 0,
    content: str | None = None,
) -> list[DocumentChunk]:
    chunk_content = document.content if content is None else content
    chunks: list[DocumentChunk] = []

    for relative_index, (start_char, end_char) in enumerate(
        _fixed_window_spans(
            content_length=len(chunk_content),
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
    ):
        chunks.append(
            _build_chunk(
                document,
                document_index=document_index,
                chunk_index=chunk_index_offset + relative_index,
                start_char=start_char_offset + start_char,
                end_char=start_char_offset + end_char,
            )
        )

    return chunks


def _markdown_section_spans(content: str) -> list[_SectionSpan]:
    heading_positions: list[int] = []
    inside_fence = False
    cursor = 0

    for line in content.splitlines(keepends=True):
        if _FENCE_RE.match(line):
            inside_fence = not inside_fence
        elif not inside_fence and _ATX_HEADING_RE.match(line):
            heading_positions.append(cursor)
        cursor += len(line)

    if not heading_positions:
        return []

    spans: list[_SectionSpan] = []
    if heading_positions[0] > 0:
        spans.append(_SectionSpan(start_char=0, end_char=heading_positions[0]))

    for index, start_char in enumerate(heading_positions):
        end_char = heading_positions[index + 1] if index + 1 < len(heading_positions) else len(content)
        spans.append(_SectionSpan(start_char=start_char, end_char=end_char))

    return [span for span in spans if span.start_char < span.end_char]


def _chunk_document_markdown_sections(
    document: SourceDocument,
    *,
    max_chars: int,
    overlap_chars: int,
    document_index: int,
) -> list[DocumentChunk]:
    if document.file_type != "markdown":
        return _chunk_document_fixed_windows(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            document_index=document_index,
        )

    section_spans = _markdown_section_spans(document.content)
    if not section_spans:
        return _chunk_document_fixed_windows(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            document_index=document_index,
        )

    chunks: list[DocumentChunk] = []
    next_chunk_index = 0

    for span in section_spans:
        section_length = span.end_char - span.start_char
        if section_length <= max_chars:
            chunks.append(
                _build_chunk(
                    document,
                    document_index=document_index,
                    chunk_index=next_chunk_index,
                    start_char=span.start_char,
                    end_char=span.end_char,
                )
            )
            next_chunk_index += 1
            continue

        section_chunks = _chunk_document_fixed_windows(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            document_index=document_index,
            chunk_index_offset=next_chunk_index,
            start_char_offset=span.start_char,
            content=document.content[span.start_char : span.end_char],
        )
        chunks.extend(section_chunks)
        next_chunk_index += len(section_chunks)

    return chunks


def chunk_document(
    document: SourceDocument,
    *,
    strategy: str = "fixed-windows",
    max_chars: int,
    overlap_chars: int,
    document_index: int = 0,
) -> list[DocumentChunk]:
    _validate_chunking_inputs(max_chars=max_chars, overlap_chars=overlap_chars)
    normalized_strategy = _normalize_strategy(strategy)

    if not document.content:
        return []

    if normalized_strategy == "fixed-windows":
        return _chunk_document_fixed_windows(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            document_index=document_index,
        )

    return _chunk_document_markdown_sections(
        document,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        document_index=document_index,
    )


def chunk_documents(
    documents: Iterable[SourceDocument],
    *,
    strategy: str = "fixed-windows",
    max_chars: int,
    overlap_chars: int,
) -> list[DocumentChunk]:
    _validate_chunking_inputs(max_chars=max_chars, overlap_chars=overlap_chars)
    normalized_strategy = _normalize_strategy(strategy)

    chunks: list[DocumentChunk] = []
    for document_index, document in enumerate(documents):
        chunks.extend(
            chunk_document(
                document,
                strategy=normalized_strategy,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                document_index=document_index,
            )
        )
    return chunks

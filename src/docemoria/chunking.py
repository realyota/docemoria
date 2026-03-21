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
    heading_title: str | None = None
    heading_level: int | None = None
    heading_path: tuple[str, ...] | None = None

    @property
    def character_count(self) -> int:
        return len(self.content)


SUPPORTED_CHUNKING_STRATEGIES = {"fixed-windows", "markdown-sections"}
_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")
_FENCE_RE = re.compile(r"^[ \t]*```")


@dataclass(slots=True)
class _Heading:
    start_char: int
    level: int
    title: str
    path: tuple[str, ...]


@dataclass(slots=True)
class _SectionSpan:
    start_char: int
    end_char: int
    heading_title: str | None = None
    heading_level: int | None = None
    heading_path: tuple[str, ...] | None = None


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
    heading_title: str | None = None,
    heading_level: int | None = None,
    heading_path: tuple[str, ...] | None = None,
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
        heading_title=heading_title,
        heading_level=heading_level,
        heading_path=heading_path,
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
    heading_title: str | None = None,
    heading_level: int | None = None,
    heading_path: tuple[str, ...] | None = None,
    heading_anchors: list[_Heading] | None = None,
) -> list[DocumentChunk]:
    chunk_content = document.content if content is None else content
    chunks: list[DocumentChunk] = []
    heading_index = -1

    for relative_index, (start_char, end_char) in enumerate(
        _fixed_window_spans(
            content_length=len(chunk_content),
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
    ):
        absolute_start_char = start_char_offset + start_char
        chunk_heading_title = heading_title
        chunk_heading_level = heading_level
        chunk_heading_path = heading_path
        if (
            chunk_heading_title is None
            and chunk_heading_level is None
            and chunk_heading_path is None
            and heading_anchors is not None
        ):
            while (
                heading_index + 1 < len(heading_anchors)
                and heading_anchors[heading_index + 1].start_char <= absolute_start_char
            ):
                heading_index += 1
            if heading_index >= 0:
                chunk_heading_title = heading_anchors[heading_index].title
                chunk_heading_level = heading_anchors[heading_index].level
                chunk_heading_path = heading_anchors[heading_index].path
        chunks.append(
            _build_chunk(
                document,
                document_index=document_index,
                chunk_index=chunk_index_offset + relative_index,
                start_char=absolute_start_char,
                end_char=start_char_offset + end_char,
                heading_title=chunk_heading_title,
                heading_level=chunk_heading_level,
                heading_path=chunk_heading_path,
            )
        )

    return chunks


def _parse_heading_line(line: str) -> tuple[int, str] | None:
    match = _ATX_HEADING_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None

    title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
    if not title:
        return None
    return len(match.group(1)), title


def _markdown_headings(content: str) -> list[_Heading]:
    headings: list[_Heading] = []
    inside_fence = False
    cursor = 0
    levels: list[str | None] = [None] * 6

    for line in content.splitlines(keepends=True):
        if _FENCE_RE.match(line):
            inside_fence = not inside_fence
        elif not inside_fence:
            parsed_heading = _parse_heading_line(line)
            if parsed_heading is not None:
                level, title = parsed_heading
                for index in range(level - 1, 6):
                    levels[index] = None
                levels[level - 1] = title
                heading_path = tuple(part for part in levels[:level] if part is not None)
                headings.append(_Heading(start_char=cursor, level=level, title=title, path=heading_path))
        cursor += len(line)

    return headings


def _markdown_section_spans(content: str, headings: list[_Heading]) -> list[_SectionSpan]:
    if not headings:
        return []

    spans: list[_SectionSpan] = []
    if headings[0].start_char > 0:
        spans.append(_SectionSpan(start_char=0, end_char=headings[0].start_char))

    for index, heading in enumerate(headings):
        end_char = headings[index + 1].start_char if index + 1 < len(headings) else len(content)
        spans.append(
            _SectionSpan(
                start_char=heading.start_char,
                end_char=end_char,
                heading_title=heading.title,
                heading_level=heading.level,
                heading_path=heading.path,
            )
        )

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

    headings = _markdown_headings(document.content)
    if not headings:
        return _chunk_document_fixed_windows(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            document_index=document_index,
        )
    section_spans = _markdown_section_spans(document.content, headings)

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
                    heading_title=span.heading_title,
                    heading_level=span.heading_level,
                    heading_path=span.heading_path,
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
            heading_title=span.heading_title,
            heading_level=span.heading_level,
            heading_path=span.heading_path,
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
        heading_anchors: list[_Heading] | None = None
        if document.file_type == "markdown":
            heading_anchors = _markdown_headings(document.content)
        return _chunk_document_fixed_windows(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            document_index=document_index,
            heading_anchors=heading_anchors,
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

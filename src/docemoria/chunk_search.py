from __future__ import annotations

import json
from dataclasses import dataclass

from .storage import StorageError


@dataclass(slots=True)
class ChunkSearchResult:
    run_id: int
    source_id: str
    document_index: int
    chunk_index: int
    repo_relative_path: str
    document_title: str | None
    heading_title: str | None
    heading_path: list[str] | None
    character_count: int
    content: str


@dataclass(slots=True)
class ChunkContextChunk:
    run_id: int
    source_id: str
    document_index: int
    chunk_index: int
    repo_relative_path: str
    document_title: str | None
    heading_title: str | None
    heading_path: list[str] | None
    character_count: int
    content: str
    is_match: bool


@dataclass(slots=True)
class ChunkContextResult:
    run_id: int
    source_id: str
    document_index: int
    repo_relative_path: str
    document_title: str | None
    match_chunk_indexes: list[int]
    chunks: list[ChunkContextChunk]


@dataclass(slots=True)
class ChunkSectionResult:
    run_id: int
    source_id: str
    document_index: int
    repo_relative_path: str
    document_title: str | None
    heading_title: str | None
    heading_path: list[str] | None
    match_chunk_indexes: list[int]
    chunks: list[ChunkContextChunk]


def _parse_heading_path(value: object) -> list[str] | None:
    if value is None:
        return None

    serialized = str(value).strip()
    if not serialized:
        return None

    try:
        parsed = json.loads(serialized)
    except json.JSONDecodeError:
        return [serialized]

    if not isinstance(parsed, list):
        return [str(parsed)]
    return [str(part) for part in parsed]


def _map_chunk_search_result_row(row: tuple[object, ...]) -> ChunkSearchResult:
    return ChunkSearchResult(
        run_id=int(row[0]),
        source_id=str(row[1]),
        document_index=int(row[2]),
        chunk_index=int(row[3]),
        repo_relative_path=str(row[4]),
        document_title=None if row[5] is None else str(row[5]),
        heading_title=None if row[6] is None else str(row[6]),
        heading_path=_parse_heading_path(row[7]),
        character_count=int(row[8]),
        content=str(row[9]),
    )


def _heading_group_key(match: ChunkSearchResult) -> tuple[str, ...]:
    if match.heading_path:
        return tuple(match.heading_path)

    if match.heading_title is not None:
        heading_title = match.heading_title.strip()
        if heading_title:
            return (heading_title,)

    return ()


def _nearest_match_distance(chunk_index: int, match_chunk_indexes: list[int]) -> int:
    if not match_chunk_indexes:
        return 0
    return min(abs(chunk_index - match_chunk_index) for match_chunk_index in match_chunk_indexes)


def _limit_section_chunks(
    *,
    section_chunks: list[ChunkContextChunk],
    match_chunk_indexes: list[int],
    max_section_chars: int | None,
) -> list[ChunkContextChunk]:
    if max_section_chars is None:
        return list(section_chunks)

    total_section_chars = sum(max(chunk.character_count, 0) for chunk in section_chunks)
    if total_section_chars <= max_section_chars:
        return list(section_chunks)

    matches = [chunk for chunk in section_chunks if chunk.is_match]
    non_matches = [chunk for chunk in section_chunks if not chunk.is_match]
    non_matches.sort(key=lambda chunk: (_nearest_match_distance(chunk.chunk_index, match_chunk_indexes), chunk.chunk_index))

    selected_chunks: list[ChunkContextChunk] = []
    selected_chunk_indexes: set[int] = set()
    selected_chars = 0

    for chunk in matches:
        if chunk.chunk_index in selected_chunk_indexes:
            continue
        next_chars = selected_chars + max(chunk.character_count, 0)
        if next_chars > max_section_chars:
            continue
        selected_chunks.append(chunk)
        selected_chunk_indexes.add(chunk.chunk_index)
        selected_chars = next_chars

    if selected_chunks:
        for chunk in non_matches:
            if chunk.chunk_index in selected_chunk_indexes:
                continue
            next_chars = selected_chars + max(chunk.character_count, 0)
            if next_chars > max_section_chars:
                continue
            selected_chunks.append(chunk)
            selected_chunk_indexes.add(chunk.chunk_index)
            selected_chars = next_chars

    return sorted(selected_chunks, key=lambda chunk: chunk.chunk_index)


def search_persisted_chunks(
    connection: "duckdb.DuckDBPyConnection",
    *,
    query: str,
    source_id: str | None = None,
    run_id: int | None = None,
    limit: int = 5,
) -> list[ChunkSearchResult]:
    if connection is None:
        raise StorageError("DuckDB connection is required to search persisted chunks")

    query_text = query.strip()
    if not query_text:
        raise StorageError("Query must be a non-empty string")

    if limit < 1:
        raise StorageError("Limit must be greater than 0")

    filters = ["strpos(lower(content), lower(?)) > 0"]
    params: list[object] = [query_text]

    if source_id is not None:
        source_id_text = source_id.strip()
        if not source_id_text:
            raise StorageError("source_id filter must be a non-empty string when provided")
        filters.append("source_id = ?")
        params.append(source_id_text)

    if run_id is not None:
        filters.append("run_id = ?")
        params.append(run_id)

    params.append(limit)
    where_clause = " AND ".join(filters)

    try:
        rows = connection.execute(
            f"""
            SELECT
                run_id,
                source_id,
                document_index,
                chunk_index,
                repo_relative_path,
                document_title,
                heading_title,
                heading_path,
                character_count,
                content
            FROM chunks
            WHERE {where_clause}
            ORDER BY run_id DESC, source_id ASC, document_index ASC, chunk_index ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError("Could not search persisted chunks in DuckDB") from exc

    return [_map_chunk_search_result_row(row) for row in rows]


def search_persisted_chunk_sections(
    connection: "duckdb.DuckDBPyConnection",
    *,
    query: str,
    source_id: str | None = None,
    run_id: int | None = None,
    limit: int = 5,
    max_section_chars: int | None = None,
) -> list[ChunkSectionResult]:
    if isinstance(max_section_chars, bool) or (
        max_section_chars is not None and not isinstance(max_section_chars, int)
    ):
        raise StorageError("max_section_chars must be greater than 0 when provided")
    if max_section_chars is not None and max_section_chars < 1:
        raise StorageError("max_section_chars must be greater than 0 when provided")

    matches = search_persisted_chunks(
        connection,
        query=query,
        source_id=source_id,
        run_id=run_id,
        limit=limit,
    )
    if not matches:
        return []

    grouped_matches: dict[tuple[int, str, int, tuple[str, ...]], list[ChunkSearchResult]] = {}
    ordered_keys: list[tuple[int, str, int, tuple[str, ...]]] = []
    for match in matches:
        key = (match.run_id, match.source_id, match.document_index, _heading_group_key(match))
        if key not in grouped_matches:
            grouped_matches[key] = []
            ordered_keys.append(key)
        grouped_matches[key].append(match)

    grouped_sections: list[ChunkSectionResult] = []
    document_chunk_cache: dict[tuple[int, str, int], list[ChunkSearchResult]] = {}

    for key in ordered_keys:
        section_matches = grouped_matches[key]
        first_match = section_matches[0]
        match_chunk_indexes = sorted({match.chunk_index for match in section_matches})
        match_chunk_index_set = set(match_chunk_indexes)
        document_key = (first_match.run_id, first_match.source_id, first_match.document_index)

        document_chunks = document_chunk_cache.get(document_key)
        if document_chunks is None:
            document_chunks = _fetch_document_chunks(
                connection,
                run_id=first_match.run_id,
                source_id=first_match.source_id,
                document_index=first_match.document_index,
            )
            document_chunk_cache[document_key] = document_chunks

        section_heading_key = key[3]
        section_chunks: list[ChunkContextChunk] = []
        for chunk in document_chunks:
            if _heading_group_key(chunk) != section_heading_key:
                continue
            section_chunks.append(
                ChunkContextChunk(
                    run_id=chunk.run_id,
                    source_id=chunk.source_id,
                    document_index=chunk.document_index,
                    chunk_index=chunk.chunk_index,
                    repo_relative_path=chunk.repo_relative_path,
                    document_title=chunk.document_title,
                    heading_title=chunk.heading_title,
                    heading_path=None if chunk.heading_path is None else list(chunk.heading_path),
                    character_count=chunk.character_count,
                    content=chunk.content,
                    is_match=chunk.chunk_index in match_chunk_index_set,
                )
            )
        bounded_section_chunks = _limit_section_chunks(
            section_chunks=section_chunks,
            match_chunk_indexes=match_chunk_indexes,
            max_section_chars=max_section_chars,
        )
        bounded_match_chunk_indexes = [
            chunk.chunk_index for chunk in bounded_section_chunks if chunk.is_match
        ]

        grouped_sections.append(
            ChunkSectionResult(
                run_id=first_match.run_id,
                source_id=first_match.source_id,
                document_index=first_match.document_index,
                repo_relative_path=first_match.repo_relative_path,
                document_title=first_match.document_title,
                heading_title=first_match.heading_title,
                heading_path=None if first_match.heading_path is None else list(first_match.heading_path),
                match_chunk_indexes=bounded_match_chunk_indexes,
                chunks=bounded_section_chunks,
            )
        )

    return grouped_sections


def _fetch_document_chunks(
    connection: "duckdb.DuckDBPyConnection",
    *,
    run_id: int,
    source_id: str,
    document_index: int,
) -> list[ChunkSearchResult]:
    try:
        rows = connection.execute(
            """
            SELECT
                run_id,
                source_id,
                document_index,
                chunk_index,
                repo_relative_path,
                document_title,
                heading_title,
                heading_path,
                character_count,
                content
            FROM chunks
            WHERE run_id = ?
              AND source_id = ?
              AND document_index = ?
            ORDER BY chunk_index ASC
            """,
            [run_id, source_id, document_index],
        ).fetchall()
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError("Could not load document chunks for context expansion") from exc

    return [_map_chunk_search_result_row(row) for row in rows]


def search_persisted_chunk_context(
    connection: "duckdb.DuckDBPyConnection",
    *,
    query: str,
    source_id: str | None = None,
    run_id: int | None = None,
    limit: int = 5,
    sibling_chunks_before: int = 1,
    sibling_chunks_after: int = 1,
) -> list[ChunkContextResult]:
    if sibling_chunks_before < 0:
        raise StorageError("sibling_chunks_before must be greater than or equal to 0")
    if sibling_chunks_after < 0:
        raise StorageError("sibling_chunks_after must be greater than or equal to 0")

    matches = search_persisted_chunks(
        connection,
        query=query,
        source_id=source_id,
        run_id=run_id,
        limit=limit,
    )
    if not matches:
        return []

    grouped_matches: dict[tuple[int, str, int], list[ChunkSearchResult]] = {}
    ordered_keys: list[tuple[int, str, int]] = []
    for match in matches:
        key = (match.run_id, match.source_id, match.document_index)
        if key not in grouped_matches:
            grouped_matches[key] = []
            ordered_keys.append(key)
        grouped_matches[key].append(match)

    grouped_context: list[ChunkContextResult] = []
    for key in ordered_keys:
        run_id_value, source_id_value, document_index_value = key
        document_matches = grouped_matches[key]
        match_chunk_indexes = sorted({match.chunk_index for match in document_matches})
        match_chunk_index_set = set(match_chunk_indexes)

        context_chunk_indexes: set[int] = set()
        for chunk_index in match_chunk_indexes:
            start_index = max(0, chunk_index - sibling_chunks_before)
            end_index = chunk_index + sibling_chunks_after
            context_chunk_indexes.update(range(start_index, end_index + 1))

        document_chunks = _fetch_document_chunks(
            connection,
            run_id=run_id_value,
            source_id=source_id_value,
            document_index=document_index_value,
        )

        context_chunks: list[ChunkContextChunk] = []
        for chunk in document_chunks:
            if chunk.chunk_index not in context_chunk_indexes:
                continue
            context_chunks.append(
                ChunkContextChunk(
                    run_id=chunk.run_id,
                    source_id=chunk.source_id,
                    document_index=chunk.document_index,
                    chunk_index=chunk.chunk_index,
                    repo_relative_path=chunk.repo_relative_path,
                    document_title=chunk.document_title,
                    heading_title=chunk.heading_title,
                    heading_path=None if chunk.heading_path is None else list(chunk.heading_path),
                    character_count=chunk.character_count,
                    content=chunk.content,
                    is_match=chunk.chunk_index in match_chunk_index_set,
                )
            )

        first_match = document_matches[0]
        grouped_context.append(
            ChunkContextResult(
                run_id=first_match.run_id,
                source_id=first_match.source_id,
                document_index=first_match.document_index,
                repo_relative_path=first_match.repo_relative_path,
                document_title=first_match.document_title,
                match_chunk_indexes=match_chunk_indexes,
                chunks=context_chunks,
            )
        )

    return grouped_context

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

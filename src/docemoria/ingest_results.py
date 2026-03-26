from __future__ import annotations

from dataclasses import dataclass

from .storage import StorageError


@dataclass(slots=True)
class IngestRunSummary:
    run_id: int
    source_id: str
    status: str
    started_at: str
    finished_at: str | None
    document_count: int
    chunk_count: int
    persisted_document_count: int
    persisted_chunk_count: int
    persisted_chunk_heading_path_count: int
    error_message: str | None


def resolve_latest_successful_run_id(
    connection: "duckdb.DuckDBPyConnection",
    source_id: str,
) -> int:
    """Return the most recent successful run_id for the given source."""
    if connection is None:
        raise StorageError("DuckDB connection is required to resolve latest successful run")

    source_id_text = source_id.strip()
    if not source_id_text:
        raise StorageError("source_id must be a non-empty string when resolving latest run")

    try:
        row = connection.execute(
            """
            SELECT run_id
            FROM ingest_runs
            WHERE source_id = ?
              AND status = 'success'
            ORDER BY run_id DESC
            LIMIT 1
            """,
            [source_id_text],
        ).fetchone()
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError("Could not resolve latest successful ingest run from DuckDB") from exc

    if row is None or row[0] is None:
        raise StorageError(f"No successful ingest runs found for source_id: {source_id_text}")

    return int(row[0])


def _map_ingest_run_summary_row(row: tuple[object, ...]) -> IngestRunSummary:
    return IngestRunSummary(
        run_id=int(row[0]),
        source_id=str(row[1]),
        status=str(row[2]),
        started_at=str(row[3]),
        finished_at=None if row[4] is None else str(row[4]),
        document_count=int(row[5]),
        chunk_count=int(row[6]),
        persisted_document_count=int(row[7]),
        persisted_chunk_count=int(row[8]),
        persisted_chunk_heading_path_count=int(row[9]),
        error_message=None if row[10] is None else str(row[10]),
    )


def _fetch_ingest_run_rows(
    connection: "duckdb.DuckDBPyConnection",
    *,
    where_clause: str = "",
    params: list[int] | None = None,
    limit: int,
) -> list[tuple[object, ...]]:
    if connection is None:
        raise StorageError("DuckDB connection is required to read ingest run summaries")
    if limit < 1:
        raise StorageError("Limit must be greater than 0")

    query_params = [] if params is None else list(params)
    query_params.append(limit)

    try:
        query = f"""
            SELECT
                runs.run_id,
                runs.source_id,
                runs.status,
                CAST(runs.started_at AS VARCHAR) AS started_at,
                CAST(runs.finished_at AS VARCHAR) AS finished_at,
                runs.document_count,
                runs.chunk_count,
                COALESCE(document_counts.persisted_document_count, 0) AS persisted_document_count,
                COALESCE(chunk_counts.persisted_chunk_count, 0) AS persisted_chunk_count,
                COALESCE(chunk_heading_path_counts.persisted_chunk_heading_path_count, 0) AS persisted_chunk_heading_path_count,
                runs.error_message
            FROM ingest_runs AS runs
            LEFT JOIN (
                SELECT run_id, COUNT(*) AS persisted_document_count
                FROM documents
                GROUP BY run_id
            ) AS document_counts ON runs.run_id = document_counts.run_id
            LEFT JOIN (
                SELECT run_id, COUNT(*) AS persisted_chunk_count
                FROM chunks
                GROUP BY run_id
            ) AS chunk_counts ON runs.run_id = chunk_counts.run_id
            LEFT JOIN (
                SELECT run_id, COUNT(*) AS persisted_chunk_heading_path_count
                FROM chunks
                WHERE heading_path IS NOT NULL
                GROUP BY run_id
            ) AS chunk_heading_path_counts ON runs.run_id = chunk_heading_path_counts.run_id
            {where_clause}
            ORDER BY runs.run_id DESC
            LIMIT ?
            """
        return connection.execute(query, query_params).fetchall()
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError("Could not read ingest run summary from DuckDB") from exc


def fetch_ingest_run_summary(
    connection: "duckdb.DuckDBPyConnection",
    *,
    run_id: int | None = None,
) -> IngestRunSummary:
    where_clause = ""
    params: list[int] | None = None
    if run_id is not None:
        where_clause = "WHERE runs.run_id = ?"
        params = [run_id]

    rows = _fetch_ingest_run_rows(
        connection,
        where_clause=where_clause,
        params=params,
        limit=1,
    )
    row = rows[0] if rows else None

    if row is None:
        if run_id is None:
            raise StorageError("No ingest runs found in DuckDB")
        raise StorageError(f"Ingest run not found: {run_id}")

    return _map_ingest_run_summary_row(row)


def fetch_recent_ingest_runs(
    connection: "duckdb.DuckDBPyConnection",
    *,
    limit: int = 10,
) -> list[IngestRunSummary]:
    rows = _fetch_ingest_run_rows(connection, limit=limit)
    return [_map_ingest_run_summary_row(row) for row in rows]

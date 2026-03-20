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
    error_message: str | None


def fetch_ingest_run_summary(
    connection: "duckdb.DuckDBPyConnection",
    *,
    run_id: int | None = None,
) -> IngestRunSummary:
    if connection is None:
        raise StorageError("DuckDB connection is required to read ingest run summaries")

    where_clause = ""
    params: list[int] | None = None
    if run_id is not None:
        where_clause = "WHERE runs.run_id = ?"
        params = [run_id]

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
            {where_clause}
            ORDER BY runs.run_id DESC
            LIMIT 1
            """
        row = (
            connection.execute(query, params).fetchone()
            if params is not None
            else connection.execute(query).fetchone()
        )
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError("Could not read ingest run summary from DuckDB") from exc

    if row is None:
        if run_id is None:
            raise StorageError("No ingest runs found in DuckDB")
        raise StorageError(f"Ingest run not found: {run_id}")

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
        error_message=None if row[9] is None else str(row[9]),
    )

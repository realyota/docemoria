from __future__ import annotations

from pathlib import Path
from typing import Final

try:
    import duckdb
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only when dependency is missing.
    duckdb = None
    _DUCKDB_IMPORT_ERROR = exc
else:
    _DUCKDB_IMPORT_ERROR = None


class StorageError(ValueError):
    """Raised when DuckDB storage bootstrap cannot be completed."""


SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS ingest_runs (
        run_id BIGINT PRIMARY KEY,
        source_id TEXT NOT NULL,
        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP,
        status TEXT NOT NULL,
        document_count INTEGER NOT NULL DEFAULT 0,
        chunk_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        source_id TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        repo_path TEXT NOT NULL,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        run_id BIGINT NOT NULL,
        document_index INTEGER NOT NULL,
        source_id TEXT NOT NULL,
        repo_relative_path TEXT NOT NULL,
        absolute_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        character_count INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (run_id, document_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        run_id BIGINT NOT NULL,
        document_index INTEGER NOT NULL,
        chunk_index INTEGER NOT NULL,
        source_id TEXT NOT NULL,
        repo_relative_path TEXT NOT NULL,
        file_type TEXT NOT NULL,
        start_char INTEGER NOT NULL,
        end_char INTEGER NOT NULL,
        character_count INTEGER NOT NULL,
        heading_title TEXT,
        heading_level INTEGER,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (run_id, document_index, chunk_index)
    )
    """,
)


def open_database(db_path: str | Path) -> "duckdb.DuckDBPyConnection":
    """Open a DuckDB connection for the provided database path."""
    if duckdb is None:
        raise StorageError("DuckDB dependency is not installed") from _DUCKDB_IMPORT_ERROR

    database = str(db_path).strip()
    if not database:
        raise StorageError("DuckDB database path must be a non-empty string or Path")

    if database != ":memory:":
        resolved_path = Path(database).expanduser().resolve()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        database = str(resolved_path)

    try:
        return duckdb.connect(database=database)
    except duckdb.Error as exc:
        raise StorageError(f"Could not open DuckDB database at: {database}") from exc


def initialize_schema(connection: "duckdb.DuckDBPyConnection") -> None:
    """Create the minimal ingest schema if it does not already exist."""
    if connection is None:
        raise StorageError("DuckDB connection is required to initialize schema")

    try:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
    except Exception as exc:
        if duckdb is not None and isinstance(exc, duckdb.Error):
            raise StorageError("Could not initialize DuckDB schema") from exc
        raise

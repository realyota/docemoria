from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .chunking import DocumentChunk, chunk_documents
from .config import DocsetConfig, load_docset_config
from .discovery import discover_docset_files, resolve_docset_repo_path
from .document_loading import SourceDocument, load_documents
from .storage import StorageError, initialize_schema, open_database

DEFAULT_DB_PATH = "data/docemoria.duckdb"
_RUNNING_STATUS = "running"
_SUCCESS_STATUS = "success"


@dataclass(slots=True)
class IngestResult:
    run_id: int
    source_id: str
    document_count: int
    chunk_count: int
    db_path: str
    status: str


def _resolved_db_path(db_path: str | Path) -> str:
    text = str(db_path).strip()
    if text == ":memory:":
        return ":memory:"
    return str(Path(text).expanduser().resolve())


def _next_run_id(connection: "duckdb.DuckDBPyConnection") -> int:
    return int(connection.execute("SELECT COALESCE(MAX(run_id), 0) + 1 FROM ingest_runs").fetchone()[0])


def _insert_documents(
    connection: "duckdb.DuckDBPyConnection",
    *,
    run_id: int,
    documents: Iterable[SourceDocument],
) -> None:
    rows = [
        (
            run_id,
            index,
            document.source_id,
            document.repo_relative_path,
            str(document.absolute_path),
            document.file_type,
            document.character_count,
            document.content,
        )
        for index, document in enumerate(documents)
    ]
    if not rows:
        return

    connection.executemany(
        """
        INSERT INTO documents (
            run_id,
            document_index,
            source_id,
            repo_relative_path,
            absolute_path,
            file_type,
            character_count,
            content
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _insert_chunks(
    connection: "duckdb.DuckDBPyConnection",
    *,
    run_id: int,
    chunks: Iterable[DocumentChunk],
) -> None:
    rows = [
        (
            run_id,
            chunk.document_index,
            chunk.chunk_index,
            chunk.source_id,
            chunk.repo_relative_path,
            chunk.file_type,
            chunk.start_char,
            chunk.end_char,
            chunk.character_count,
            chunk.heading_title,
            chunk.heading_level,
            chunk.content,
        )
        for chunk in chunks
    ]
    if not rows:
        return

    connection.executemany(
        """
        INSERT INTO chunks (
            run_id,
            document_index,
            chunk_index,
            source_id,
            repo_relative_path,
            file_type,
            start_char,
            end_char,
            character_count,
            heading_title,
            heading_level,
            content
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _persist_ingest_transaction(
    connection: "duckdb.DuckDBPyConnection",
    *,
    config: DocsetConfig,
    repo_root: Path,
    documents: list[SourceDocument],
    chunks: list[DocumentChunk],
) -> int:
    try:
        connection.execute("BEGIN TRANSACTION")
        run_id = _next_run_id(connection)

        connection.execute(
            """
            INSERT INTO ingest_runs (run_id, source_id, status)
            VALUES (?, ?, ?)
            """,
            [run_id, config.source_id, _RUNNING_STATUS],
        )
        connection.execute(
            """
            INSERT INTO sources (source_id, label, repo_path)
            VALUES (?, ?, ?)
            ON CONFLICT (source_id)
            DO UPDATE SET
              label = EXCLUDED.label,
              repo_path = EXCLUDED.repo_path,
              updated_at = CURRENT_TIMESTAMP
            """,
            [config.source_id, config.label, str(repo_root)],
        )

        _insert_documents(connection, run_id=run_id, documents=documents)
        _insert_chunks(connection, run_id=run_id, chunks=chunks)

        connection.execute(
            """
            UPDATE ingest_runs
            SET
              status = ?,
              finished_at = CURRENT_TIMESTAMP,
              document_count = ?,
              chunk_count = ?,
              error_message = NULL
            WHERE run_id = ?
            """,
            [_SUCCESS_STATUS, len(documents), len(chunks), run_id],
        )
        connection.execute("COMMIT")
    except Exception as exc:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise StorageError("Could not persist ingest transaction") from exc

    return run_id


def ingest_docset(
    config_path: str | Path,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> IngestResult:
    config = load_docset_config(Path(config_path))
    repo_root = resolve_docset_repo_path(config)
    source_paths = discover_docset_files(config)
    documents = load_documents(source_paths, source_id=config.source_id, repo_root=repo_root)
    chunks = chunk_documents(
        documents,
        strategy=config.chunking.strategy,
        max_chars=config.chunking.max_chars,
        overlap_chars=config.chunking.overlap_chars,
    )

    with open_database(db_path) as connection:
        initialize_schema(connection)
        run_id = _persist_ingest_transaction(
            connection,
            config=config,
            repo_root=repo_root,
            documents=documents,
            chunks=chunks,
        )

    return IngestResult(
        run_id=run_id,
        source_id=config.source_id,
        document_count=len(documents),
        chunk_count=len(chunks),
        db_path=_resolved_db_path(db_path),
        status=_SUCCESS_STATUS,
    )

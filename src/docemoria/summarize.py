from __future__ import annotations

import hashlib
from typing import Any

from .providers.openai import OpenAIGenerationProvider


def _build_summarization_dependencies(config: Any) -> tuple[OpenAIGenerationProvider, str]:
    if config is None:
        raise ValueError("Docset config is required to summarize documents")

    providers_config = getattr(config, "providers", None)
    if providers_config is None or providers_config.generation is None:
        raise ValueError("Docset config must include a generation provider")

    provider_config = providers_config.generation
    if provider_config.provider != "openai":
        raise ValueError(f"Provider '{provider_config.provider}' is not supported for summarization")

    compression_style = str(config.prompts.compression_style).strip()
    provider = OpenAIGenerationProvider(model=provider_config.model)
    return provider, compression_style


def summarize_run(connection: "duckdb.DuckDBPyConnection", config: Any, run_id: int, verbose: bool = False) -> None:
    """Generate summaries for documents in a run and persist them in DuckDB."""
    provider, compression_style = _build_summarization_dependencies(config)
    _summarize_documents(
        connection,
        run_id,
        provider=provider,
        compression_style=compression_style,
        verbose=verbose,
    )
    summarize_run_global(
        connection,
        run_id,
        provider=provider,
        compression_style=compression_style,
        verbose=verbose,
    )


def summarize_run_global(
    connection: "duckdb.DuckDBPyConnection",
    run_id: int,
    *,
    provider: OpenAIGenerationProvider,
    compression_style: str,
    verbose: bool = False,
) -> None:
    """Create a global summary for an entire run and persist it in `ingest_runs.summary`."""
    if connection is None:
        raise ValueError("DuckDB connection is required to summarize documents")

    try:
        rows = connection.execute(
            """
            SELECT summary
            FROM documents
            WHERE run_id = ?
            ORDER BY document_index ASC
            """,
            [run_id],
        ).fetchall()
    except Exception as exc:
        raise ValueError("Could not load document summaries for global summarization") from exc

    try:
        existing_run_cursor = connection.execute(
            """
            SELECT summary, summary_input_checksum
            FROM ingest_runs
            WHERE run_id = ?
            """,
            [run_id],
        )
    except Exception as exc:
        raise ValueError("Could not load existing run summary metadata") from exc

    existing_run_rows: list[tuple[object, ...]]
    if hasattr(existing_run_cursor, "fetchone"):
        existing_run_state = existing_run_cursor.fetchone()
        if existing_run_state is not None:
            existing_run_rows = [existing_run_state]
        else:
            existing_run_rows = []
    else:  # pragma: no cover - compatibility with minimal cursor stubs
        existing_run_rows = existing_run_cursor.fetchall()

    existing_summary_checksum = None
    if existing_run_rows:
        first_row = existing_run_rows[0]
        if first_row[1] is not None:
            existing_summary_checksum = str(first_row[1])

    document_summaries = [
        str(row[0]).strip()
        for row in rows
        if row[0] is not None and str(row[0]).strip()
    ]

    if not document_summaries:
        if verbose:
            print(f"No document summaries available for run_id={run_id}; clearing run summary")
        try:
            connection.execute(
                """
                UPDATE ingest_runs
                SET summary = NULL, summary_input_checksum = NULL
                WHERE run_id = ?
                """,
                [run_id],
            )
        except Exception as exc:
            raise ValueError("Could not persist run-level summary") from exc
        return

    summary_input_checksum = _build_run_summary_checksum(
        compression_style=compression_style,
        document_summaries=document_summaries,
    )
    if existing_summary_checksum == summary_input_checksum:
        if verbose:
            print(f"Skipping run-level summary for run_id={run_id}: input unchanged")
        return

    prompt = (
        f"{compression_style}\n\nDocument Summaries:\n\n"
        f"{'\n\n'.join(document_summaries)}\n\nGlobal Knowledge Map/Summary:"
    )
    generated_summary = provider.generate(prompt)

    if verbose:
        print(f"Generated global summary for run_id={run_id}")

    try:
        connection.execute(
            """
            UPDATE ingest_runs
            SET summary = ?, summary_input_checksum = ?
            WHERE run_id = ?
            """,
            [generated_summary, summary_input_checksum, run_id],
        )
    except Exception as exc:
        raise ValueError("Could not persist run-level summary") from exc


def _build_run_summary_checksum(
    compression_style: str,
    document_summaries: list[str],
) -> str:
    payload = f"{compression_style}\n\n{'\n\n'.join(document_summaries)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summarize_documents(
    connection: "duckdb.DuckDBPyConnection",
    run_id: int,
    *,
    provider: OpenAIGenerationProvider,
    compression_style: str,
    verbose: bool = False,
) -> None:
    if connection is None:
        raise ValueError("DuckDB connection is required to summarize documents")

    try:
        rows = connection.execute(
            """
            SELECT document_index, content, content_checksum, summary, summary_checksum
            FROM documents
            WHERE run_id = ?
            ORDER BY document_index ASC
            """,
            [run_id],
        ).fetchall()
    except Exception as exc:
        raise ValueError("Could not load documents for summarization") from exc

    for row in rows:
        document_index = int(row[0])
        content = str(row[1])
        content_checksum = row[2]
        if content_checksum is None:
            content_checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        else:
            content_checksum = str(content_checksum)

        summary = None if row[3] is None else str(row[3])
        summary_checksum = None if row[4] is None else str(row[4])

        if summary is not None and summary_checksum == content_checksum:
            if verbose:
                print(f"Skipping document {document_index}: summary already up to date")
            continue

        prompt = f"{compression_style}\n\nDocument Content:\n{content}\n\nSummary:"
        generated_summary = provider.generate(prompt)

        if verbose:
            print(f"Summarized document {document_index} (run_id={run_id})")

        connection.execute(
            """
            UPDATE documents
            SET summary = ?, summary_checksum = ?
            WHERE run_id = ? AND document_index = ?
            """,
            [generated_summary, content_checksum, run_id, document_index],
        )

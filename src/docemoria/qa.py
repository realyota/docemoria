from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from docemoria.chunk_search import ChunkSectionResult, search_persisted_chunk_sections
from docemoria.config import ConfigError, load_docset_config
from docemoria.ingest_results import resolve_latest_successful_run_id
from docemoria.providers.openai import OpenAIGenerationProvider
from docemoria.storage import StorageError, open_database

DEFAULT_DB_PATH = "docemoria.db"

def _load_document_summaries(
    connection: "duckdb.DuckDBPyConnection",
    sections: list[ChunkSectionResult],
) -> dict[tuple[int, str, int], str]:
    if connection is None:
        return {}

    summaries: dict[tuple[int, str, int], str] = {}
    for section in sections:
        key = (section.run_id, section.source_id, section.document_index)
        if key in summaries:
            continue

        try:
            row = connection.execute(
                """
                SELECT summary
                FROM documents
                WHERE run_id = ? AND document_index = ?
                """,
                [section.run_id, section.document_index],
            ).fetchone()
        except Exception:
            return {}

        if row is None:
            continue

        summary = row[0]
        if summary is not None:
            summaries[key] = str(summary)
    return summaries


def _load_run_summary(
    connection: "duckdb.DuckDBPyConnection | None",
    run_id: int | None,
) -> str | None:
    if connection is None or run_id is None:
        return None

    try:
        row = connection.execute(
            """
            SELECT summary
            FROM ingest_runs
            WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()
    except Exception:
        return None

    if row is None or row[0] is None:
        return None

    return str(row[0])


def format_context(
    sections: list[ChunkSectionResult],
    *,
    connection: "duckdb.DuckDBPyConnection | None" = None,
    run_id: int | None = None,
) -> str:
    """Format retrieved sections into a context string for the LLM."""
    relevant_run_id = run_id
    if relevant_run_id is None and sections:
        relevant_run_id = sections[0].run_id

    global_summary = _load_run_summary(connection, relevant_run_id)
    summary_by_document = _load_document_summaries(connection, sections)
    context_parts = []
    if global_summary:
        context_parts.append(f"Global Context:\n{global_summary}")

    for section in sections:
        file_path = section.repo_relative_path
        summary = summary_by_document.get((section.run_id, section.source_id, section.document_index))
        summary_line = f"Summary: {summary}\n" if summary else ""
        heading = f"## {section.heading_title}" if section.heading_title else ""
        content = "\n".join(chunk.content for chunk in section.chunks)
        context_parts.append(f"File: {file_path}\n{summary_line}{heading}\n{content}")
    
    return "\n\n---\n\n".join(context_parts)


def format_sources(sections: list[ChunkSectionResult]) -> list[dict[str, Any]]:
    """Build compact, structured source references from retrieved QA sections."""
    return [
        {
            "source_id": section.source_id,
            "document_index": section.document_index,
            "file": section.repo_relative_path,
            "heading": section.heading_title,
            "heading_path": None if section.heading_path is None else list(section.heading_path),
            "match_chunk_indexes": list(section.match_chunk_indexes),
        }
        for section in sections
    ]

def build_qa_prompt(query: str, context: str, system_prompt: str = "") -> str:
    """Construct the final RAG prompt."""
    base_prompt = (
        "Use the following documentation snippets to answer the user's question.\n"
        "If the answer is not in the documentation, say you don't know.\n\n"
        f"Documentation:\n{context}\n\n"
        f"Question: {query}\n"
        "Answer:"
    )
    if system_prompt:
        return f"{system_prompt}\n\n{base_prompt}"
    return base_prompt

def perform_qa(
    config_path: Path,
    query: str,
    db_path: Path = Path(DEFAULT_DB_PATH),
    run_id: int | None = None,
    verbose: bool = False,
    include_sources: bool = False,
) -> str | tuple[str, list[dict[str, Any]]]:
    """Execute the RAG QA flow."""
    # 1. Load config
    config = load_docset_config(config_path)
    
    # 2. Retrieve relevant context
    with open_database(db_path) as conn:
        resolved_run_id = run_id
        if resolved_run_id is None:
            resolved_run_id = resolve_latest_successful_run_id(conn, source_id=config.source_id)
        sections = search_persisted_chunk_sections(
            conn,
            query=query,
            source_id=config.source_id,
            run_id=resolved_run_id,
            limit=config.retrieval.top_k,
            max_section_chars=config.retrieval.max_section_chars
        )
        context_text = format_context(sections, connection=conn, run_id=resolved_run_id)

    if not sections:
        return "No relevant documentation found for the given query."
    
    # 3. Setup Provider
    gen_config = config.providers.generation
    if not gen_config:
        return "Error: No generation provider configured for this docset."
    
    if gen_config.provider != "openai":
        return f"Error: Provider '{gen_config.provider}' is not supported for QA yet."
    
    provider = OpenAIGenerationProvider(model=gen_config.model)
    
    # 4. Generate Answer
    prompt = build_qa_prompt(query, context_text, system_prompt=config.prompts.system)
    
    if verbose:
        print("\n--- CONTEXT ---")
        print(context_text)
        print("\n--- PROMPT ---")
        print(prompt)
        print("\n--- END PROMPT ---\n")
        
    answer = provider.generate(prompt)
    if include_sources:
        return answer, format_sources(sections)
    return answer

def main() -> int:
    parser = argparse.ArgumentParser(prog="docemoria-qa")
    parser.add_argument("config_path", help="Path to a docset YAML config")
    parser.add_argument("query", help="Question to ask about the documentation")
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print retrieved context and final prompt",
    )
    
    args = parser.parse_args()
    
    try:
        answer = perform_qa(
            Path(args.config_path),
            args.query,
            db_path=Path(args.db_path),
            run_id=args.run_id,
            verbose=args.verbose
        )
        print(f"\nAnswer:\n{answer}")
        return 0
    except (ConfigError, StorageError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

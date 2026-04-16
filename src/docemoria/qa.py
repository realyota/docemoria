from __future__ import annotations

import argparse
from dataclasses import dataclass
import re
import sys
from pathlib import Path
from typing import Any
from docemoria.providers.generation import GenerationError

from docemoria.chunk_search import ChunkSectionResult, search_persisted_chunk_sections
from docemoria.config import ConfigError, load_docset_config
from docemoria.ingest_results import resolve_latest_successful_run_id
from docemoria.providers.openai import OpenAIGenerationProvider
from docemoria.storage import StorageError, open_database

DEFAULT_DB_PATH = "docemoria.db"

_CONTEXT_TRUNCATION_NOTE = "\n\n[Context truncated to keep the prompt compact.]"
_MATCH_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


@dataclass(slots=True)
class SummaryArtifact:
    source_id: str
    run_id: int
    scope: str
    document_index: int | None
    repo_relative_path: str | None
    document_title: str | None
    summary: str


def _tokenize_match_text(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in _MATCH_TOKEN_PATTERN.findall(text.lower()):
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _score_summary_match(summary: str, *, query_text: str, query_tokens: list[str]) -> tuple[int, int] | None:
    normalized_summary = summary.lower()
    exact_phrase_match = int(query_text.lower() in normalized_summary)

    if not query_tokens:
        if exact_phrase_match:
            return (exact_phrase_match, 0)
        return None

    summary_tokens = set(_tokenize_match_text(summary))
    matched_token_count = sum(1 for token in query_tokens if token in summary_tokens)
    if matched_token_count == 0 and not exact_phrase_match:
        return None

    return (exact_phrase_match, matched_token_count)


def _search_summary_artifacts(
    connection: "duckdb.DuckDBPyConnection | None",
    *,
    query: str,
    source_id: str,
    run_id: int | None,
    limit: int,
) -> list[SummaryArtifact]:
    if connection is None or run_id is None:
        return []

    query_text = query.strip()
    if not query_text:
        return []

    source_id_text = source_id.strip()
    if not source_id_text:
        return []

    if limit < 1:
        raise ValueError("top_k must be greater than 0 when provided")

    query_tokens = _tokenize_match_text(query_text)
    artifacts: list[SummaryArtifact] = []

    try:
        run_summary_row = connection.execute(
            """
            SELECT summary
            FROM ingest_runs
            WHERE run_id = ?
              AND source_id = ?
              AND summary IS NOT NULL
            """,
            [run_id, source_id_text],
        ).fetchone()
    except Exception:
        run_summary_row = None

    if run_summary_row is not None and run_summary_row[0] is not None:
        run_summary = str(run_summary_row[0])
        if _score_summary_match(
            run_summary,
            query_text=query_text,
            query_tokens=query_tokens,
        ) is not None:
            artifacts.append(
                SummaryArtifact(
                    source_id=source_id_text,
                    run_id=run_id,
                    scope="run",
                    document_index=None,
                    repo_relative_path=None,
                    document_title=None,
                    summary=run_summary,
                )
            )

    try:
        rows = connection.execute(
            """
            SELECT
                run_id,
                source_id,
                document_index,
                repo_relative_path,
                document_title,
                summary
            FROM documents
            WHERE run_id = ?
              AND source_id = ?
              AND summary IS NOT NULL
            ORDER BY document_index ASC
            """,
            [run_id, source_id_text],
        ).fetchall()
    except Exception:
        return artifacts

    scored_artifacts: list[tuple[tuple[int, int], SummaryArtifact]] = []
    for row in rows:
        summary = row[5]
        if summary is None:
            continue

        summary_text = str(summary)
        score = _score_summary_match(
            summary_text,
            query_text=query_text,
            query_tokens=query_tokens,
        )
        if score is None:
            continue

        scored_artifacts.append(
            (
                score,
                SummaryArtifact(
                    source_id=source_id_text if row[1] is None else str(row[1]),
                    run_id=run_id,
                    scope="document",
                    document_index=int(row[2]),
                    repo_relative_path=str(row[3]),
                    document_title=None if row[4] is None else str(row[4]),
                    summary=summary_text,
                ),
            )
        )

    scored_artifacts.sort(
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            item[1].document_index if item[1].document_index is not None else -1,
        )
    )
    artifacts.extend(artifact for _, artifact in scored_artifacts[:limit])
    return artifacts


def _format_summary_artifacts_context(
    artifacts: list[SummaryArtifact],
    *,
    max_context_chars: int | None = None,
) -> str:
    if not artifacts:
        return ""

    context_parts: list[str] = ["Summary artifacts matched in compact knowledge layer:"]
    for artifact in artifacts:
        if artifact.scope == "run":
            label = "Run summary"
            location = "run scope"
        else:
            label = "Document summary"
            location = artifact.repo_relative_path or "unknown"

        context_parts.append(f"{label} ({location}):\n{artifact.summary}")

    return _truncate_context("\n\n---\n\n".join(context_parts), max_context_chars=max_context_chars)


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


def _truncate_context(context_text: str, max_context_chars: int | None) -> str:
    if max_context_chars is None:
        return context_text

    if max_context_chars <= 0:
        raise ValueError("max_context_chars must be greater than 0 when provided")

    if len(context_text) <= max_context_chars:
        return context_text

    if max_context_chars <= len(_CONTEXT_TRUNCATION_NOTE):
        return context_text[:max_context_chars]

    cut_after = max_context_chars - len(_CONTEXT_TRUNCATION_NOTE)
    return context_text[:cut_after] + _CONTEXT_TRUNCATION_NOTE


def format_context(
    sections: list[ChunkSectionResult],
    *,
    connection: "duckdb.DuckDBPyConnection | None" = None,
    run_id: int | None = None,
    max_context_chars: int | None = None,
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
    
    return _truncate_context("\n\n---\n\n".join(context_parts), max_context_chars=max_context_chars)


def format_sources(sections: list[ChunkSectionResult]) -> list[dict[str, Any]]:
    """Build compact, structured source references from retrieved QA sections."""
    sources = [
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
    return sources


def format_summary_sources(artifacts: list[SummaryArtifact]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": artifact.source_id,
            "document_index": artifact.document_index,
            "file": artifact.repo_relative_path,
            "heading": "Run Summary" if artifact.scope == "run" else "Document Summary",
            "heading_path": None,
            "match_chunk_indexes": [],
            "summary_scope": artifact.scope,
        }
        for artifact in artifacts
    ]

def build_qa_prompt(query: str, context: str, system_prompt: str = "", qa_style: str = "") -> str:
    """Construct the final RAG prompt."""
    system_parts: list[str] = []
    if system_prompt:
        system_parts.append(system_prompt)
    if qa_style:
        system_parts.append(qa_style)

    system_header = "\n\n".join(system_parts)

    base_prompt = (
        "Use the following documentation snippets to answer the user's question.\n"
        "If the answer is not in the documentation, say you don't know.\n\n"
        f"Documentation:\n{context}\n\n"
        f"Question: {query}\n"
        "Answer:"
    )
    if system_header:
        return f"{system_header}\n\n{base_prompt}"
    return base_prompt

def perform_qa(
    config_path: Path,
    query: str,
    db_path: Path = Path(DEFAULT_DB_PATH),
    run_id: int | None = None,
    top_k: int | None = None,
    max_context_chars: int | None = None,
    verbose: bool = False,
    include_sources: bool = False,
) -> str | tuple[str, list[dict[str, Any]]]:
    """Execute the RAG QA flow."""
    # 1. Load config
    config = load_docset_config(config_path)

    retrieval_top_k = config.retrieval.top_k
    if top_k is not None:
        if top_k < 1:
            raise ValueError("top_k must be greater than 0 when provided")
        retrieval_top_k = top_k
    
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
            limit=retrieval_top_k,
            max_section_chars=config.retrieval.max_section_chars
        )
        summary_artifacts: list[SummaryArtifact] = []
        context_text = ""

        if sections:
            context_text = format_context(
                sections,
                connection=conn,
                run_id=resolved_run_id,
                max_context_chars=max_context_chars,
            )
        else:
            summary_artifacts = _search_summary_artifacts(
                conn,
                query=query,
                source_id=config.source_id,
                run_id=resolved_run_id,
                limit=retrieval_top_k,
            )
            if not summary_artifacts:
                return "No relevant documentation found for the given query."
            context_text = _format_summary_artifacts_context(
                summary_artifacts,
                max_context_chars=max_context_chars,
            )

    # 3. Setup Provider
    gen_config = config.providers.generation
    if not gen_config:
        return "Error: No generation provider configured for this docset."
    
    if gen_config.provider != "openai":
        return f"Error: Provider '{gen_config.provider}' is not supported for QA yet."
    
    provider = OpenAIGenerationProvider(model=gen_config.model)
    
    # 4. Generate Answer
    prompt = build_qa_prompt(
        query,
        context_text,
        system_prompt=config.prompts.system,
        qa_style=config.prompts.qa_style,
    )
    
    if verbose:
        print("\n--- CONTEXT ---")
        print(context_text)
        print("\n--- PROMPT ---")
        print(prompt)
        print("\n--- END PROMPT ---\n")
        
    answer = provider.generate(prompt)
    if include_sources:
        if sections:
            return answer, format_sources(sections)
        return answer, format_summary_sources(summary_artifacts)
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
    except GenerationError as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

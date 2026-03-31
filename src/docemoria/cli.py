from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .chunk_search import (
    ChunkContextChunk,
    ChunkContextResult,
    ChunkSearchResult,
    ChunkSectionResult,
    search_persisted_chunk_context,
    search_persisted_chunk_sections,
    search_persisted_chunks,
)
from .chunking import ChunkingError, DocumentChunk, chunk_documents
from .config import ConfigError, load_docset_config, load_docset_configs
from .discovery import DiscoveryError, discover_docset_files, resolve_docset_repo_path
from .document_loading import DocumentLoadingError, SourceDocument, load_documents
from .ingest import DEFAULT_DB_PATH, ingest_docset
from .ingest_results import fetch_ingest_run_summary, fetch_recent_ingest_runs
from .qa import perform_qa
from .storage import StorageError, initialize_schema, open_database
from .summarize import summarize_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docemoria")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-docsets", help="List configured docsets")
    list_parser.add_argument(
        "--configs-dir",
        default="configs/docsets",
        help="Directory containing docset YAML configs",
    )

    validate_parser = subparsers.add_parser("show-docset", help="Load and print a single docset config")
    validate_parser.add_argument("config_path", help="Path to a docset YAML config")

    discover_parser = subparsers.add_parser(
        "list-source-files",
        help="List source files selected for ingest from one docset",
    )
    discover_parser.add_argument("config_path", help="Path to a docset YAML config")

    preview_parser = subparsers.add_parser(
        "preview-documents",
        help="Load discovered markdown/text source documents and print a JSON preview",
    )
    preview_parser.add_argument("config_path", help="Path to a docset YAML config")
    preview_parser.add_argument(
        "--include-content",
        action="store_true",
        help="Include full document text in the JSON output",
    )

    chunk_preview_parser = subparsers.add_parser(
        "preview-chunks",
        help="Load documents, chunk them, and print a JSON preview",
    )
    chunk_preview_parser.add_argument("config_path", help="Path to a docset YAML config")

    init_db_parser = subparsers.add_parser(
        "init-db",
        help="Create a DuckDB database file and initialize the minimal ingest schema",
    )
    init_db_parser.add_argument("db_path", help="Path to the DuckDB database file")

    ingest_parser = subparsers.add_parser(
        "ingest-docset",
        help="Run full ingest for one docset and persist results to DuckDB",
    )
    ingest_parser.add_argument("config_path", help="Path to a docset YAML config")
    ingest_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )

    show_ingest_parser = subparsers.add_parser(
        "show-ingest-run",
        help="Show one persisted ingest run summary from DuckDB (latest by default)",
    )
    show_ingest_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    show_ingest_parser.add_argument(
        "--run-id",
        type=int,
        help="Specific ingest run_id to inspect (default: latest run)",
    )

    list_ingest_parser = subparsers.add_parser(
        "list-ingest-runs",
        help="List recent persisted ingest runs from DuckDB",
    )
    list_ingest_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    list_ingest_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of recent runs to include (default: 10)",
    )

    search_chunks_parser = subparsers.add_parser(
        "search-chunks",
        help="Search persisted chunk content in DuckDB with optional source/run filters",
    )
    search_chunks_parser.add_argument("query", help="Substring query to search for in chunk content")
    search_chunks_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    search_chunks_parser.add_argument(
        "--source-id",
        help="Optional source_id filter to restrict matching chunks",
    )
    search_chunks_parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter to restrict matching chunks",
    )
    search_chunks_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of matching chunks to include (default: 5)",
    )

    search_context_parser = subparsers.add_parser(
        "search-context",
        help=(
            "Search persisted chunks and expand each document match with nearby sibling chunks "
            "from the same run/document"
        ),
    )
    search_context_parser.add_argument("query", help="Substring query to search for in chunk content")
    search_context_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    search_context_parser.add_argument(
        "--source-id",
        help="Optional source_id filter to restrict matching chunks",
    )
    search_context_parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter to restrict matching chunks",
    )
    search_context_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of matching chunks to include before grouping (default: 5)",
    )
    search_context_parser.add_argument(
        "--before",
        type=int,
        default=1,
        help="Number of sibling chunks to include before each matching chunk (default: 1)",
    )
    search_context_parser.add_argument(
        "--after",
        type=int,
        default=1,
        help="Number of sibling chunks to include after each matching chunk (default: 1)",
    )

    search_sections_parser = subparsers.add_parser(
        "search-sections",
        help=(
            "Search persisted chunks, group by section metadata, and return full section chunk "
            "context with match flags"
        ),
    )
    search_sections_parser.add_argument("query", help="Substring query to search for in chunk content")
    search_sections_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    search_sections_parser.add_argument(
        "--source-id",
        help="Optional source_id filter to restrict matching chunks",
    )
    search_sections_parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter to restrict matching chunks",
    )
    search_sections_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of matching chunks to include before grouping (default: 5)",
    )
    search_sections_parser.add_argument(
        "--max-section-chars",
        type=int,
        help="Optional positive character budget per returned section",
    )

    retrieve_context_parser = subparsers.add_parser(
        "retrieve-context",
        help=(
            "Load a docset config and retrieve section-grouped persisted chunk context "
            "using docset retrieval defaults"
        ),
    )
    retrieve_context_parser.add_argument("config_path", help="Path to a docset YAML config")
    retrieve_context_parser.add_argument("query", help="Substring query to search for in chunk content")
    retrieve_context_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    retrieve_context_parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter to restrict matching chunks",
    )

    retrieve_neighbors_parser = subparsers.add_parser(
        "retrieve-neighbors",
        help=(
            "Load a docset config and retrieve sibling chunk context "
            "using docset retrieval defaults"
        ),
    )
    retrieve_neighbors_parser.add_argument("config_path", help="Path to a docset YAML config")
    retrieve_neighbors_parser.add_argument("query", help="Substring query to search for in chunk content")
    retrieve_neighbors_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    retrieve_neighbors_parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter to restrict matching chunks",
    )

    qa_parser = subparsers.add_parser(
        "ask",
        help="Ask a question over documentation using LLM + RAG",
    )
    qa_parser.add_argument("config_path", help="Path to a docset YAML config")
    qa_parser.add_argument("query", help="Question to ask")
    qa_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    qa_parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter",
    )
    qa_parser.add_argument(
        "--max-context-chars",
        type=int,
        help="Optional max total context characters passed to the QA prompt",
    )
    qa_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print retrieved context and final prompt",
    )
    qa_parser.add_argument(
        "--with-sources",
        action="store_true",
        help="Print structured source references used to build the answer",
    )

    summarize_parser = subparsers.add_parser(
        "summarize-run",
        help="Generate document and global summaries for one persisted ingest run",
    )
    summarize_parser.add_argument("config_path", help="Path to a docset YAML config")
    summarize_parser.add_argument("run_id", type=int, help="Ingest run_id to summarize")
    summarize_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )

    return parser


def _document_preview_payload(document: SourceDocument, *, include_content: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": document.source_id,
        "absolute_path": str(document.absolute_path),
        "repo_relative_path": document.repo_relative_path,
        "file_type": document.file_type,
        "document_title": document.document_title,
        "character_count": document.character_count,
    }
    if include_content:
        payload["content"] = document.content
    return payload


def _chunk_preview_payload(chunk: DocumentChunk) -> dict[str, object]:
    return {
        "source_id": chunk.source_id,
        "absolute_path": str(chunk.absolute_path),
        "repo_relative_path": chunk.repo_relative_path,
        "file_type": chunk.file_type,
        "document_index": chunk.document_index,
        "chunk_index": chunk.chunk_index,
        "start_char": chunk.start_char,
        "end_char": chunk.end_char,
        "character_count": chunk.character_count,
        "document_title": chunk.document_title,
        "heading_title": chunk.heading_title,
        "heading_level": chunk.heading_level,
        "heading_path": None if chunk.heading_path is None else list(chunk.heading_path),
        "content": chunk.content,
    }


def _chunk_search_payload(result: ChunkSearchResult) -> dict[str, object]:
    return {
        "run_id": result.run_id,
        "source_id": result.source_id,
        "document_index": result.document_index,
        "chunk_index": result.chunk_index,
        "repo_relative_path": result.repo_relative_path,
        "document_title": result.document_title,
        "heading_title": result.heading_title,
        "heading_path": None if result.heading_path is None else list(result.heading_path),
        "character_count": result.character_count,
        "content": result.content,
    }


def _chunk_context_chunk_payload(chunk: ChunkContextChunk) -> dict[str, object]:
    return {
        "run_id": chunk.run_id,
        "source_id": chunk.source_id,
        "document_index": chunk.document_index,
        "chunk_index": chunk.chunk_index,
        "repo_relative_path": chunk.repo_relative_path,
        "document_title": chunk.document_title,
        "heading_title": chunk.heading_title,
        "heading_path": None if chunk.heading_path is None else list(chunk.heading_path),
        "character_count": chunk.character_count,
        "content": chunk.content,
        "is_match": chunk.is_match,
    }


def _chunk_context_payload(result: ChunkContextResult) -> dict[str, object]:
    return {
        "run_id": result.run_id,
        "source_id": result.source_id,
        "document_index": result.document_index,
        "repo_relative_path": result.repo_relative_path,
        "document_title": result.document_title,
        "match_chunk_indexes": list(result.match_chunk_indexes),
        "chunk_count": len(result.chunks),
        "chunks": [_chunk_context_chunk_payload(chunk) for chunk in result.chunks],
    }


def _chunk_section_payload(result: ChunkSectionResult) -> dict[str, object]:
    return {
        "run_id": result.run_id,
        "source_id": result.source_id,
        "document_index": result.document_index,
        "repo_relative_path": result.repo_relative_path,
        "document_title": result.document_title,
        "heading_title": result.heading_title,
        "heading_path": None if result.heading_path is None else list(result.heading_path),
        "match_chunk_indexes": list(result.match_chunk_indexes),
        "chunk_count": len(result.chunks),
        "chunks": [_chunk_context_chunk_payload(chunk) for chunk in result.chunks],
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "list-docsets":
            configs = load_docset_configs(Path(args.configs_dir))
            payload = [asdict(config) for config in configs]
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "show-docset":
            config = load_docset_config(Path(args.config_path))
            print(json.dumps(asdict(config), indent=2))
            return 0

        if args.command == "list-source-files":
            config = load_docset_config(Path(args.config_path))
            repo_root = resolve_docset_repo_path(config)
            for path in discover_docset_files(config):
                print(path.relative_to(repo_root).as_posix())
            return 0

        if args.command == "preview-documents":
            config = load_docset_config(Path(args.config_path))
            documents = load_documents(config)
            payload = {
                "source_id": config.source_id,
                "document_count": len(documents),
                "documents": [
                    _document_preview_payload(document, include_content=args.include_content)
                    for document in documents
                ],
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "preview-chunks":
            config = load_docset_config(Path(args.config_path))
            documents = load_documents(config)
            chunks = chunk_documents(
                documents,
                strategy=config.chunking.strategy,
                max_chars=config.chunking.max_chars,
                overlap_chars=config.chunking.overlap_chars,
            )
            payload = {
                "source_id": config.source_id,
                "document_count": len(documents),
                "chunk_count": len(chunks),
                "chunking": {
                    "strategy": config.chunking.strategy,
                    "max_chars": config.chunking.max_chars,
                    "overlap_chars": config.chunking.overlap_chars,
                },
                "chunks": [_chunk_preview_payload(chunk) for chunk in chunks],
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "init-db":
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
            payload = {
                "db_path": str(Path(args.db_path).expanduser().resolve()),
                "schema_initialized": True,
                "tables": ["ingest_runs", "sources", "documents", "chunks"],
            }
            print(json.dumps(payload, indent=2))
            return 0

        if args.command == "ingest-docset":
            result = ingest_docset(Path(args.config_path), db_path=Path(args.db_path))
            payload = {
                "run_id": result.run_id,
                "source_id": result.source_id,
                "document_count": result.document_count,
                "chunk_count": result.chunk_count,
                "db_path": result.db_path,
                "status": result.status,
            }
            print(json.dumps(payload, separators=(",", ":")))
            return 0

        if args.command == "show-ingest-run":
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                summary = fetch_ingest_run_summary(connection, run_id=args.run_id)
            print(json.dumps(asdict(summary), separators=(",", ":")))
            return 0

        if args.command == "list-ingest-runs":
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                summaries = fetch_recent_ingest_runs(connection, limit=args.limit)
            print(json.dumps([asdict(summary) for summary in summaries], separators=(",", ":")))
            return 0

        if args.command == "search-chunks":
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                matches = search_persisted_chunks(
                    connection,
                    query=args.query,
                    source_id=args.source_id,
                    run_id=args.run_id,
                    limit=args.limit,
                )
            payload = {
                "query": args.query,
                "filters": {
                    "source_id": args.source_id,
                    "run_id": args.run_id,
                    "limit": args.limit,
                },
                "match_count": len(matches),
                "matches": [_chunk_search_payload(match) for match in matches],
            }
            print(json.dumps(payload, separators=(",", ":")))
            return 0

        if args.command == "search-context":
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                grouped_matches = search_persisted_chunk_context(
                    connection,
                    query=args.query,
                    source_id=args.source_id,
                    run_id=args.run_id,
                    limit=args.limit,
                    sibling_chunks_before=args.before,
                    sibling_chunks_after=args.after,
                )
            payload = {
                "query": args.query,
                "filters": {
                    "source_id": args.source_id,
                    "run_id": args.run_id,
                    "limit": args.limit,
                },
                "context_window": {
                    "before": args.before,
                    "after": args.after,
                },
                "group_count": len(grouped_matches),
                "groups": [_chunk_context_payload(match) for match in grouped_matches],
            }
            print(json.dumps(payload, separators=(",", ":")))
            return 0

        if args.command == "search-sections":
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                grouped_matches = search_persisted_chunk_sections(
                    connection,
                    query=args.query,
                    source_id=args.source_id,
                    run_id=args.run_id,
                    limit=args.limit,
                    max_section_chars=args.max_section_chars,
                )
            payload = {
                "query": args.query,
                "filters": {
                    "source_id": args.source_id,
                    "run_id": args.run_id,
                    "limit": args.limit,
                    "max_section_chars": args.max_section_chars,
                },
                "group_count": len(grouped_matches),
                "groups": [_chunk_section_payload(match) for match in grouped_matches],
            }
            print(json.dumps(payload, separators=(",", ":")))
            return 0

        if args.command == "retrieve-context":
            config = load_docset_config(Path(args.config_path))
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                grouped_matches = search_persisted_chunk_sections(
                    connection,
                    query=args.query,
                    source_id=config.source_id,
                    run_id=args.run_id,
                    limit=config.retrieval.top_k,
                    max_section_chars=config.retrieval.max_section_chars,
                )
            payload = {
                "query": args.query,
                "docset": {
                    "config_path": str(Path(args.config_path)),
                    "source_id": config.source_id,
                    "label": config.label,
                },
                "filters": {
                    "source_id": config.source_id,
                    "run_id": args.run_id,
                    "limit": config.retrieval.top_k,
                    "max_section_chars": config.retrieval.max_section_chars,
                },
                "group_count": len(grouped_matches),
                "groups": [_chunk_section_payload(match) for match in grouped_matches],
            }
            print(json.dumps(payload, separators=(",", ":")))
            return 0

        if args.command == "retrieve-neighbors":
            config = load_docset_config(Path(args.config_path))
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                grouped_matches = search_persisted_chunk_context(
                    connection,
                    query=args.query,
                    source_id=config.source_id,
                    run_id=args.run_id,
                    limit=config.retrieval.top_k,
                    sibling_chunks_before=config.retrieval.context_before_chunks,
                    sibling_chunks_after=config.retrieval.context_after_chunks,
                )
            payload = {
                "query": args.query,
                "docset": {
                    "config_path": str(Path(args.config_path)),
                    "source_id": config.source_id,
                    "label": config.label,
                },
                "filters": {
                    "source_id": config.source_id,
                    "run_id": args.run_id,
                    "limit": config.retrieval.top_k,
                },
                "context_window": {
                    "before": config.retrieval.context_before_chunks,
                    "after": config.retrieval.context_after_chunks,
                },
                "group_count": len(grouped_matches),
                "groups": [_chunk_context_payload(match) for match in grouped_matches],
            }
            print(json.dumps(payload, separators=(",", ":")))
            return 0

        if args.command == "ask":
            result = perform_qa(
                Path(args.config_path),
                args.query,
                db_path=Path(args.db_path),
                run_id=args.run_id,
                max_context_chars=args.max_context_chars,
                verbose=args.verbose,
                include_sources=args.with_sources,
            )
            if args.with_sources and isinstance(result, tuple):
                answer, sources = result
                print(answer)
                print(json.dumps({"sources": sources}, separators=(",", ":")))
            else:
                print(result)
            return 0

        if args.command == "summarize-run":
            config = load_docset_config(Path(args.config_path))
            with open_database(Path(args.db_path)) as connection:
                initialize_schema(connection)
                summarize_run(connection, config, run_id=args.run_id, verbose=False)
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except (ChunkingError, ConfigError, DiscoveryError, DocumentLoadingError, StorageError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .chunking import ChunkingError, DocumentChunk, chunk_documents
from .config import ConfigError, load_docset_config, load_docset_configs
from .discovery import DiscoveryError, discover_docset_files, resolve_docset_repo_path
from .document_loading import DocumentLoadingError, SourceDocument, load_documents
from .ingest import DEFAULT_DB_PATH, ingest_docset
from .ingest_results import fetch_ingest_run_summary, fetch_recent_ingest_runs
from .storage import StorageError, initialize_schema, open_database


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

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except (ChunkingError, ConfigError, DiscoveryError, DocumentLoadingError, StorageError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

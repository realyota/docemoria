from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .config import ConfigError, load_docset_config, load_docset_configs
from .discovery import DiscoveryError, discover_docset_files, resolve_docset_repo_path
from .document_loading import DocumentLoadingError, SourceDocument, load_documents


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

    return parser


def _document_preview_payload(document: SourceDocument, *, include_content: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": document.source_id,
        "absolute_path": str(document.absolute_path),
        "repo_relative_path": document.repo_relative_path,
        "file_type": document.file_type,
        "character_count": document.character_count,
    }
    if include_content:
        payload["content"] = document.content
    return payload


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

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except (ConfigError, DiscoveryError, DocumentLoadingError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .config import load_docset_config, load_docset_configs


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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list-docsets":
        configs = load_docset_configs(Path(args.configs_dir))
        payload = [asdict(config) for config in configs]
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "show-docset":
        config = load_docset_config(Path(args.config_path))
        print(json.dumps(asdict(config), indent=2))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

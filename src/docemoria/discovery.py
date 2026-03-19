from __future__ import annotations

from pathlib import Path, PurePosixPath

from .config import DocsetConfig


class DiscoveryError(ValueError):
    """Raised when source file discovery cannot run for a docset."""


def resolve_docset_repo_path(config: DocsetConfig) -> Path:
    config_path = Path(config.config_path)
    if config.config_path and not config_path.is_absolute():
        config_path = config_path.resolve()

    repo_path = Path(config.repo_path)
    if repo_path.is_absolute():
        return repo_path

    if config.config_path:
        return (config_path.parent / repo_path).resolve()

    return repo_path.resolve()


def _matches_any_pattern(path: Path, patterns: list[str]) -> bool:
    posix_path = PurePosixPath(path.as_posix())
    path_text = posix_path.as_posix()
    for pattern in patterns:
        if posix_path.match(pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if path_text == prefix or path_text.startswith(f"{prefix}/"):
                return True
    return False


def discover_docset_files(config: DocsetConfig) -> list[Path]:
    repo_root = resolve_docset_repo_path(config)
    if not repo_root.exists():
        raise DiscoveryError(f"Docset repo path does not exist: {repo_root}")
    if not repo_root.is_dir():
        raise DiscoveryError(f"Docset repo path is not a directory: {repo_root}")

    included: set[Path] = set()
    for pattern in config.ingest.include_globs:
        included.update(path.resolve() for path in repo_root.glob(pattern) if path.is_file())

    files = [
        path
        for path in included
        if not _matches_any_pattern(path.relative_to(repo_root), config.ingest.exclude_globs)
    ]
    return sorted(files, key=lambda path: path.relative_to(repo_root).as_posix())

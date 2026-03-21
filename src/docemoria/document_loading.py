from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from .checksums import stable_content_checksum
from .config import DocsetConfig
from .discovery import discover_docset_files, resolve_docset_repo_path


class DocumentLoadingError(ValueError):
    """Raised when source documents cannot be loaded into memory."""


_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")


@dataclass(slots=True)
class SourceDocument:
    source_id: str
    absolute_path: Path
    repo_relative_path: str
    content: str
    file_type: str
    document_title: str | None = None

    @property
    def character_count(self) -> int:
        return len(self.content)

    @property
    def content_checksum(self) -> str:
        return stable_content_checksum(self.content)


def _detect_file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix == ".txt":
        return "text"
    raise DocumentLoadingError(f"Unsupported source file type for loading: {path}")


def _resolve_load_inputs(
    source: DocsetConfig | Iterable[Path],
    *,
    source_id: str | None,
    repo_root: Path | None,
) -> tuple[str, Path, list[Path]]:
    if isinstance(source, DocsetConfig):
        resolved_repo_root = resolve_docset_repo_path(source)
        return source.source_id, resolved_repo_root, discover_docset_files(source)

    if source_id is None or not source_id.strip():
        raise DocumentLoadingError("source_id is required when loading explicit source file paths")
    if repo_root is None:
        raise DocumentLoadingError("repo_root is required when loading explicit source file paths")

    resolved_repo_root = repo_root.resolve()
    paths = [Path(path).resolve() for path in source]
    return source_id.strip(), resolved_repo_root, paths


def _read_utf8_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentLoadingError(f"Source file is not valid UTF-8 text: {path}") from exc
    except OSError as exc:
        raise DocumentLoadingError(f"Could not read source file: {path}") from exc


def _extract_markdown_title(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _ATX_HEADING_RE.match(stripped)
        if match is None:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        return title or None
    return None


def _extract_text_title(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _extract_document_title(*, content: str, file_type: str) -> str | None:
    if file_type == "markdown":
        return _extract_markdown_title(content)
    if file_type == "text":
        return _extract_text_title(content)
    return None


def load_documents(
    source: DocsetConfig | Iterable[Path],
    *,
    source_id: str | None = None,
    repo_root: Path | None = None,
) -> list[SourceDocument]:
    resolved_source_id, resolved_repo_root, paths = _resolve_load_inputs(
        source,
        source_id=source_id,
        repo_root=repo_root,
    )

    documents: list[SourceDocument] = []
    for path in paths:
        resolved_path = path.resolve()
        file_type = _detect_file_type(resolved_path)

        try:
            repo_relative_path = resolved_path.relative_to(resolved_repo_root).as_posix()
        except ValueError as exc:
            raise DocumentLoadingError(
                f"Source file is outside the repo root '{resolved_repo_root}': {resolved_path}"
            ) from exc

        content = _read_utf8_text(resolved_path)

        documents.append(
            SourceDocument(
                source_id=resolved_source_id,
                absolute_path=resolved_path,
                repo_relative_path=repo_relative_path,
                content=content,
                file_type=file_type,
                document_title=_extract_document_title(content=content, file_type=file_type),
            )
        )

    return documents

"""Docemoria core package."""

from .config import DocsetConfig, load_docset_config, load_docset_configs
from .discovery import DiscoveryError, discover_docset_files, resolve_docset_repo_path
from .document_loading import DocumentLoadingError, SourceDocument, load_documents
from .storage import StorageError, initialize_schema, open_database

__all__ = [
    "DocsetConfig",
    "DiscoveryError",
    "DocumentLoadingError",
    "SourceDocument",
    "StorageError",
    "discover_docset_files",
    "initialize_schema",
    "open_database",
    "resolve_docset_repo_path",
    "load_documents",
    "load_docset_config",
    "load_docset_configs",
]

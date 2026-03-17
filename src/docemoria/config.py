from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a docset config is invalid."""


@dataclass(slots=True)
class PromptConfig:
    system: str = ""
    notes_style: str = ""


@dataclass(slots=True)
class ProviderModelConfig:
    provider: str
    model: str


@dataclass(slots=True)
class ProvidersConfig:
    embeddings: ProviderModelConfig | None = None
    generation: ProviderModelConfig | None = None


@dataclass(slots=True)
class ChunkingConfig:
    strategy: str = "markdown-sections"
    max_chars: int = 1800
    overlap_chars: int = 200


@dataclass(slots=True)
class RetrievalConfig:
    top_k: int = 8
    rerank: bool = True


@dataclass(slots=True)
class CardGenerationConfig:
    preferred_types: list[str] = field(default_factory=lambda: ["qa"])
    difficulty: str = "medium"
    audience: str = "intermediate"


@dataclass(slots=True)
class ExportConfig:
    obsidian_path: str = "outputs/obsidian"
    anki_path: str = "outputs/anki"


@dataclass(slots=True)
class DocsetConfig:
    source_id: str
    label: str
    repo_path: str
    enabled: bool = True
    prompts: PromptConfig = field(default_factory=PromptConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    card_generation: CardGenerationConfig = field(default_factory=CardGenerationConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    config_path: str = ""


REQUIRED_TOP_LEVEL_FIELDS = ("source_id", "label", "repo_path")


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a mapping: {path}")

    return data


def _require_string(data: dict[str, Any], key: str, *, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Field '{key}' must be a non-empty string in {path}")
    return value.strip()


def _optional_mapping(data: dict[str, Any], key: str, *, path: Path) -> dict[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Field '{key}' must be a mapping in {path}")
    return value


def _parse_provider_model(data: dict[str, Any], section_name: str, *, path: Path) -> ProviderModelConfig | None:
    if not data:
        return None
    return ProviderModelConfig(
        provider=_require_string(data, "provider", path=path),
        model=_require_string(data, "model", path=path),
    )


def _validate_no_unknown_missing_basics(data: dict[str, Any], *, path: Path) -> None:
    for key in REQUIRED_TOP_LEVEL_FIELDS:
        if key not in data:
            raise ConfigError(f"Missing required field '{key}' in {path}")


def load_docset_config(path: Path) -> DocsetConfig:
    raw = _read_yaml(path)
    _validate_no_unknown_missing_basics(raw, path=path)

    prompts = _optional_mapping(raw, "prompts", path=path)
    providers = _optional_mapping(raw, "providers", path=path)
    chunking = _optional_mapping(raw, "chunking", path=path)
    retrieval = _optional_mapping(raw, "retrieval", path=path)
    card_generation = _optional_mapping(raw, "card_generation", path=path)
    export = _optional_mapping(raw, "export", path=path)

    return DocsetConfig(
        source_id=_require_string(raw, "source_id", path=path),
        label=_require_string(raw, "label", path=path),
        repo_path=_require_string(raw, "repo_path", path=path),
        enabled=bool(raw.get("enabled", True)),
        prompts=PromptConfig(
            system=str(prompts.get("system", "")).strip(),
            notes_style=str(prompts.get("notes_style", "")).strip(),
        ),
        providers=ProvidersConfig(
            embeddings=_parse_provider_model(
                _optional_mapping(providers, "embeddings", path=path),
                "embeddings",
                path=path,
            ),
            generation=_parse_provider_model(
                _optional_mapping(providers, "generation", path=path),
                "generation",
                path=path,
            ),
        ),
        chunking=ChunkingConfig(
            strategy=str(chunking.get("strategy", "markdown-sections")),
            max_chars=int(chunking.get("max_chars", 1800)),
            overlap_chars=int(chunking.get("overlap_chars", 200)),
        ),
        retrieval=RetrievalConfig(
            top_k=int(retrieval.get("top_k", 8)),
            rerank=bool(retrieval.get("rerank", True)),
        ),
        card_generation=CardGenerationConfig(
            preferred_types=list(card_generation.get("preferred_types", ["qa"])),
            difficulty=str(card_generation.get("difficulty", "medium")),
            audience=str(card_generation.get("audience", "intermediate")),
        ),
        export=ExportConfig(
            obsidian_path=str(export.get("obsidian_path", "outputs/obsidian")),
            anki_path=str(export.get("anki_path", "outputs/anki")),
        ),
        config_path=str(path),
    )


def load_docset_configs(configs_dir: Path) -> list[DocsetConfig]:
    if not configs_dir.exists():
        raise ConfigError(f"Configs directory does not exist: {configs_dir}")

    configs: list[DocsetConfig] = []
    for path in sorted(configs_dir.glob("*.y*ml")):
        config = load_docset_config(path)
        if config.enabled:
            configs.append(config)
    return configs

# Docset Config Format

Docemoria's first concrete implementation seam is the **docset config**.

A docset config describes one local documentation source and the defaults that should travel with it:

- where the source repo lives
- whether it is enabled
- prompt overrides
- provider defaults
- chunking defaults
- retrieval defaults
- card generation preferences
- export targets

## File location

Store configs in:

```text
configs/docsets/*.yaml
```

## Minimal example

```yaml
source_id: python-docs
label: Python Docs
repo_path: docsets/python-docs
enabled: true
```

## Full example

See `configs/docsets/example.yaml`.

## Supported fields

### Required

- `source_id`: stable machine-readable identifier
- `label`: human-readable name
- `repo_path`: path to the local checked-out docs repo

### Optional

- `enabled`: defaults to `true`
- `prompts.system`
- `prompts.notes_style`
- `providers.embeddings.provider`
- `providers.embeddings.model`
- `providers.generation.provider`
- `providers.generation.model`
- `chunking.strategy`
- `chunking.max_chars`
- `chunking.overlap_chars`
- `retrieval.top_k`
- `retrieval.rerank`
- `card_generation.preferred_types`
- `card_generation.difficulty`
- `card_generation.audience`
- `export.obsidian_path`
- `export.anki_path`

## CLI

List enabled docsets:

```bash
PYTHONPATH=src python3 -m docemoria.cli list-docsets
```

Show one resolved config:

```bash
PYTHONPATH=src python3 -m docemoria.cli show-docset configs/docsets/example.yaml
```

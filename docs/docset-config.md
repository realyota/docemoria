# Docset Config Format

Docemoria's first concrete implementation seam is the **docset config**.

A docset config describes one local documentation source and the defaults that should travel with it:

- where the source repo lives
- whether it is enabled
- file selection rules for ingest
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
repo_path: ../../docsets/python-docs
enabled: true
```

## Full example

See `configs/docsets/example.yaml`.

## Supported fields

### Required

- `source_id`: stable machine-readable identifier
- `label`: human-readable name
- `repo_path`: path to the local checked-out docs repo; relative paths are resolved from the config file location

### Optional

- `enabled`: defaults to `true`
- `ingest.include_globs`: glob patterns to include during ingest, defaults to `['**/*.md', '**/*.txt']`
- `ingest.exclude_globs`: glob patterns to skip during ingest, defaults to `[]`
- `prompts.system`
- `prompts.notes_style`
- `prompts.qa_style`: task-specific guidance for future documentation Q&A flows
- `prompts.compression_style`: task-specific guidance for future compressed knowledge artifact generation
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

## Ingest file selection

The optional `ingest` section lets a docset narrow which files should enter the pipeline before parsing and chunking.

Example:

```yaml
ingest:
  include_globs:
    - docs/**/*.md
    - reference/**/*.txt
  exclude_globs:
    - docs/archive/**
    - '**/node_modules/**'
```

This keeps ingest practical for MVP work:

- include the parts of a repo that are actually documentation,
- exclude vendored, generated, archived, or irrelevant paths,
- keep downstream study-material generation and future Q&A grounded in better source selection.

## Prompt structure

The `prompts` section is intentionally split so a docset can steer different downstream tasks without requiring separate config files.

- `system`: broad, docset-level behavior shared across generation tasks
- `notes_style`: style guidance for learning notes and review-oriented outputs
- `qa_style`: answer-shaping guidance for future LLM + RAG question-answering
- `compression_style`: distillation guidance for future compressed knowledge artifacts

All prompt fields are optional and default to empty strings, so existing configs remain valid.

## CLI

List enabled docsets:

```bash
PYTHONPATH=src python3 -m docemoria.cli list-docsets
```

Show one resolved config:

```bash
PYTHONPATH=src python3 -m docemoria.cli show-docset configs/docsets/example.yaml
```

Preview source files selected for ingest from one docset:

```bash
PYTHONPATH=src python3 -m docemoria.cli list-source-files configs/docsets/example.yaml
```

This command resolves `repo_path`, applies `ingest.include_globs`, removes matches from `ingest.exclude_globs`, and prints the final repo-relative file list that would enter the ingest pipeline.

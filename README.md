# 📚 Docemoria

Docemoria is a learning-first system for turning **local technical documentation** into **study materials** and a **compressed knowledge layer**.

Instead of building yet another generic knowledge base, the goal is to create a practical pipeline that reads documentation from local repositories and produces:

- 🧠 **Anki-style flashcards**
- 🔁 **spaced-repetition notes**
- 📝 **Obsidian-friendly learning outputs**
- 💬 **LLM-assisted answers over documentation via RAG**
- 🗜️ **compressed knowledge artifacts distilled from raw docs**

---

## ✨ What problem it solves

Technical documentation is full of useful knowledge, but it is usually optimized for **reference**, not **retention**, and not for **fast question-answering at the right level of abstraction**.

That creates several practical problems:

1. raw docs are hard to turn into durable memory,
2. useful facts are buried inside long pages and repeated across sections,
3. naive RAG often retrieves too much raw text and too little distilled understanding,
4. teams and individuals lack a compact, reusable knowledge layer built from the docs they actually use,
5. study workflows and operational question-answering are usually treated as separate systems even though they should reinforce each other.

Docemoria aims to bridge that gap by:

1. reading documentation from local checkouts,
2. parsing and chunking the content,
3. indexing and ranking useful knowledge fragments,
4. compressing documentation into higher-value knowledge artifacts,
5. generating study materials from that knowledge,
6. answering questions over the documentation with LLM + RAG,
7. exporting outputs into tools people actually use for learning and recall.

The project is meant to convert raw docs into something you can **query, review, memorize, and revisit over time**.

---

## 🎯 Project goals

Docemoria is designed around a few clear goals:

- build a **working MVP quickly**
- keep onboarding of new docsets **simple**
- generate **high-quality learning materials**, not generic summaries
- support **useful question-answering over docs** with LLM + RAG
- build a **compressed knowledge base** from source documentation, not only a chunk index
- avoid hard-locking the system to a single provider or a single documentation source
- keep the architecture practical and easy to evolve

---

## 🧱 Core idea

The system should work roughly like this:

### 1. 📥 Ingest
Read one or more local documentation repositories attached as `git submodules`.

### 2. ✂️ Parse and chunk
Extract readable content, split it into meaningful chunks, and preserve useful metadata.

### 3. 🗂️ Store and index
Persist source metadata, documents, chunks, embeddings, compressed knowledge artifacts, and processing state in a simple storage layer.

### 4. 🗜️ Build a compressed knowledge layer
Distill raw documentation into higher-value units such as:

- compact concept summaries
- operational notes
- mechanism explanations
- constraints / limits / defaults
- troubleshooting knowledge
- terminology and relationship maps

### 5. 💬 Answer questions with LLM + RAG
Use both raw chunks and compressed knowledge artifacts to answer user questions more effectively than raw retrieval alone.

### 6. 🎓 Generate learning material
Create different types of educational outputs such as:

- definition cards
- question/answer cards
- cloze cards
- concept summaries
- troubleshooting-oriented learning notes
- syntax and workflow reminders

### 7. 📤 Export
Write the results into formats that are immediately useful in real workflows, especially:

- Obsidian markdown
- Anki-friendly export formats

---

## 🏗️ Architecture principles

Docemoria is intentionally opinionated in a few ways.

### Local-first sources
- Documentation sources are expected to live in local repositories.
- These repositories can be attached as `git submodules`.
- The system should operate on the local checkout directly.

### Per-docset configurability
Each docset should be able to define its own:

- configuration
- system prompt
- generation style
- retrieval behavior
- compression behavior
- content-specific heuristics

Different documentation sets require different treatment. API docs, architecture docs, and troubleshooting docs should not all produce the same kind of learning material or compressed knowledge artifacts.

### Simple storage first
- Primary storage: **DuckDB**
- Keep the data model practical and inspectable
- Favor simplicity over premature distributed complexity

Current Milestone 1 storage bootstrap is intentionally small and provides two APIs:
- `open_database(db_path)` to open a local DuckDB file (creating parent directories when needed),
- `initialize_schema(connection)` to create the core ingest tables:
  `ingest_runs`, `sources`, `documents`, `chunks`.

### Provider abstraction
The system should separate:

- **embeddings provider**
- **generation provider**

Default starting assumptions:

- embeddings: `OpenAI text-embedding-3`
- generation: `gpt-5.4`

But the architecture should make it easy to swap providers and models later.

---

## 🧠 Why this is not “just RAG”

Docemoria should support question-answering over docs with LLM + RAG, but it is not only a general-purpose ask-anything-over-docs system.

The focus is broader:

- retrieving answers when the user asks questions,
- identifying what is worth learning,
- transforming it into reviewable knowledge,
- building a compressed knowledge layer from the source material,
- and supporting long-term retention.

That means chunk selection, prompting, ranking, summarization, and export should be optimized for **learning quality and knowledge compression**, not just answer accuracy.

---

## 🗺️ MVP direction

The rough MVP path is:

### Milestone 1 — Ingest MVP
- detect a docset from config
- scan files
- parse markdown / text
- chunk content
- store documents and chunks in DuckDB

### Milestone 2 — Generation MVP
- implement provider abstraction
- add initial OpenAI-backed generation flow
- support base prompt + per-docset prompt
- generate first useful flashcards, review notes, and compressed knowledge artifacts

### Milestone 3 — Export MVP
- export markdown for Obsidian
- export Anki-friendly output
- produce outputs per docset / per run

### Milestone 4 — Retrieval quality + Q&A MVP
- add embeddings
- improve retrieval quality
- apply reranking / heuristics
- improve chunk selection for card generation
- add a basic LLM + RAG question-answering flow
- use compressed knowledge artifacts alongside raw chunks when useful

### Milestone 5 — Multi-docset support
- support multiple docsets cleanly
- track updates by commit hash / checksum
- keep configuration source-specific and maintainable

---

## 📂 Repository direction

The repository is expected to evolve toward a structure along these lines:

```text
configs/
  docsets/

src/
  ingest/
  parsing/
  chunking/
  storage/
  retrieval/
  generation/
  export/

outputs/

docs/
```

This structure is not final, but the intent is clear:

- keep docset config easy to find,
- keep the pipeline modular,
- keep outputs inspectable,
- keep the MVP small enough to actually finish.

---

## 🔧 Configuration philosophy

A new docset should be easy to add.

At minimum, a docset config should eventually describe:

- source repository location
- file/include rules
- file/exclude rules
- parsing strategy
- chunking strategy
- prompt overrides
- card-generation preferences
- export targets

The system should support a layered prompt model:

- global base prompt
- per-docset prompt
- task-specific prompt

A docset config should also be able to influence:

- question-answering behavior
- knowledge compression style
- preferred educational outputs

---

## ✅ Design priorities

In order:

1. **Simple, working MVP**
2. **Easy configuration for new docsets**
3. **Good learning-material quality**
4. **Useful compressed knowledge + Q&A behavior**
5. **Provider flexibility**

If a choice makes the MVP dramatically harder without a strong immediate payoff, it is probably the wrong choice.

---

## 🚧 Current status

This repository is currently in the **project-definition / architecture-shaping** stage, but now includes an initial implementation for **docset config loading**.

The main focus right now is:

- clarifying the architecture,
- choosing practical implementation steps,
- keeping the project general rather than overfitting to one documentation set,
- turning the planned docset configuration format into executable code.

Current implemented slice:

- Python package scaffold in `src/docemoria/`
- YAML-backed docset config loader and validator
- per-docset ingest file selection rules (`include_globs` / `exclude_globs`)
- source file discovery that resolves `repo_path` and applies ingest globs
- minimal document loader that reads discovered UTF-8 `.md` / `.txt` files into an in-memory document model, including best-effort `document_title` extraction and stable document content checksums
- chunk preview flow with `fixed-windows` and `markdown-sections` strategies, including stable chunk content checksums
- minimal DuckDB storage bootstrap for the first ingest schema (`ingest_runs`, `sources`, `documents`, `chunks`) with persisted content checksum fields for future change tracking
- simple CLI to list docsets, inspect a single config, preview selected source files/documents/chunks, initialize the database schema, run ingest, inspect one persisted ingest result (`show-ingest-run`), and list recent ingest results (`list-ingest-runs`)
- ingest inspection command:
  - `docemoria show-ingest-run --db-path ./data/docemoria.duckdb` (latest run)
  - `docemoria show-ingest-run --db-path ./data/docemoria.duckdb --run-id 7` (specific run)
  - `docemoria list-ingest-runs --db-path ./data/docemoria.duckdb --limit 10` (recent runs)
- initial tests for config loading, discovery, document loading, chunking, storage bootstrap, and CLI behavior
- config format notes in `docs/docset-config.md`

---

## 🤝 Intended use cases

Docemoria should eventually work well for things like:

- learning a large technical product from its docs
- turning ops / infra docs into review material
- building repeatable study decks from evolving documentation
- generating Obsidian learning notes from engineering sources
- answering practical questions over documentation with better-than-naive RAG
- building a compact knowledge layer for recurring operational and conceptual questions
- supporting structured review of complex documentation over time

---

## 💡 Working principle

**Practical implementation beats elaborate theory.**

This project prefers:

- concrete steps over brainstorming,
- simple storage over unnecessary complexity,
- reviewable outputs over magic,
- real learning value over flashy demos.

---

## 📌 Summary

Docemoria is a system for converting **local documentation repositories** into **high-quality study material**, **compressed knowledge artifacts**, and **better question-answering over docs**.

It is built around:

- 📂 local doc repositories
- 🦆 DuckDB storage
- 🧩 configurable per-docset behavior
- 🔌 provider abstraction
- 🧠 learning-first output generation
- 🗜️ compressed knowledge construction
- 💬 LLM + RAG question-answering
- 📝 export to Obsidian / Anki-friendly formats

If it works well, it should make technical documentation not only searchable, but actually **learnable, reusable, and easier to query**.

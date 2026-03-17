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

Technical documentation is full of useful knowledge, but it is usually optimized for **reference**, not **retention**.

Docemoria aims to bridge that gap:

1. read documentation from local checkouts,
2. parse and chunk the content,
3. index and rank useful knowledge fragments,
4. generate study materials from them,
5. export those materials into tools people actually use for learning.

The project is meant to help convert raw docs into something you can **review, memorize, and revisit over time**.

---

## 🎯 Project goals

Docemoria is designed around a few clear goals:

- build a **working MVP quickly**
- keep onboarding of new docsets **simple**
- generate **high-quality learning materials**, not generic summaries
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
Persist source metadata, documents, chunks, embeddings, and processing state in a simple storage layer.

### 4. 🎓 Generate learning material
Create different types of educational outputs such as:

- definition cards
- question/answer cards
- cloze cards
- concept summaries
- troubleshooting-oriented learning notes
- syntax and workflow reminders

### 5. 📤 Export
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
- content-specific heuristics

Different documentation sets require different treatment. API docs, architecture docs, and troubleshooting docs should not all produce the same kind of learning material.

### Simple storage first
- Primary storage: **DuckDB**
- Keep the data model practical and inspectable
- Favor simplicity over premature distributed complexity

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
- generate first useful flashcards and review notes

### Milestone 3 — Export MVP
- export markdown for Obsidian
- export Anki-friendly output
- produce outputs per docset / per run

### Milestone 4 — Retrieval quality
- add embeddings
- improve retrieval quality
- apply reranking / heuristics
- improve chunk selection for card generation

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
- parsing strategy
- chunking strategy
- prompt overrides
- card-generation preferences
- export targets

The system should support a layered prompt model:

- global base prompt
- per-docset prompt
- task-specific prompt

---

## ✅ Design priorities

In order:

1. **Simple, working MVP**
2. **Easy configuration for new docsets**
3. **Good learning-material quality**
4. **Provider flexibility**

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
- simple CLI to list docsets or inspect a single config
- initial tests for config loading behavior
- config format notes in `docs/docset-config.md`

---

## 🤝 Intended use cases

Docemoria should eventually work well for things like:

- learning a large technical product from its docs
- turning ops / infra docs into review material
- building repeatable study decks from evolving documentation
- generating Obsidian learning notes from engineering sources
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

Docemoria is a system for converting **local documentation repositories** into **high-quality study material**.

It is built around:

- 📂 local doc repositories
- 🦆 DuckDB storage
- 🧩 configurable per-docset behavior
- 🔌 provider abstraction
- 🧠 learning-first output generation
- 📝 export to Obsidian / Anki-friendly formats

If it works well, it should make technical documentation not only searchable, but actually **learnable**.

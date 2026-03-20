# ROADMAP.md - Docemoria

## Stan repo na 2026-03-19

Zaimplementowane w kodzie:

- ładowanie i walidacja configów docsetów (`configs/docsets/*.yaml`)
- ingest file selection (`ingest.include_globs` / `ingest.exclude_globs`)
- discovery plików źródłowych z poprawnym rozwiązywaniem `repo_path`
- ładowanie dokumentów `.md` / `.txt` do modelu in-memory
- chunking:
  - `fixed-windows`
  - `markdown-sections`
  - metadata nagłówków (`heading_title`, `heading_level`)
- minimalny bootstrap storage na DuckDB:
  - otwieranie bazy
  - inicjalizacja schematu `ingest_runs` / `sources` / `documents` / `chunks`
- CLI:
  - `list-docsets`
  - `show-docset`
  - `list-source-files`
  - `preview-documents`
  - `preview-chunks`
  - `init-db`
- testy jednostkowe dla config/loading/chunking/storage/CLI

Braki względem Ingest MVP:

- brak warstwy storage (DuckDB)
- brak trwałego zapisu `sources/documents/chunks`
- brak `ingest run` i historii przetworzeń
- brak komendy CLI uruchamiającej pełny ingest end-to-end

## Milestone 1 — Ingest MVP (dokończenie)

Cel: trwały ingest 1 docsetu end-to-end do DuckDB.

Zakres zakończony:

- [x] config docsetu + walidacja
- [x] discovery plików
- [x] loading dokumentów
- [x] chunking dokumentów

Zakres do zrobienia (w kolejności implementacji):

- [x] dodać zależność `duckdb` i moduł `storage`
- [x] zdefiniować minimalny schemat tabel:
  - `ingest_runs`
  - `sources`
  - `documents`
  - `chunks`
- [ ] wdrożyć zapis ingestu w transakcji (`discover -> load -> chunk -> persist`)
- [ ] dodać komendę CLI `ingest-docset <config_path> [--db-path ...]`
- [ ] dodać podstawowy raport wyników ingestu (run id, document_count, chunk_count)
- [ ] dodać test integracyjny ingestu z tymczasową bazą DuckDB
- [ ] zaktualizować dokumentację uruchomienia ingestu

Definition of Done (Milestone 1):

- jedna komenda CLI zapisuje wyniki ingestu do DuckDB
- po zakończeniu da się odczytać dokumenty i chunki z DB
- testy integracyjne przechodzą lokalnie

## Milestone 2 — Generation MVP

Cel: wygenerować pierwsze użyteczne materiały edukacyjne z chunków.

- [ ] interfejs provider abstraction dla generation
- [ ] implementacja startowa OpenAI (model konfigurowalny per docset)
- [ ] obsługa promptów: base + per-docset + task-specific
- [ ] generowanie:
  - flashcards (minimum: `qa`, `cloze`)
  - krótkich notatek do powtórek
- [ ] zapis wyników generation do DuckDB
- [ ] komenda CLI `generate-materials`

## Milestone 3 — Export MVP

Cel: wygenerowane materiały są gotowe do użycia poza systemem.

- [ ] eksport markdown do Obsidiana
- [ ] eksport CSV pod Anki
- [ ] struktura output per `docset` / `run`
- [ ] testy snapshotowe dla eksportu

## Milestone 4 — Retrieval + Q&A MVP

Cel: odpowiedzi na pytania oparte na dokumentacji i skompresowanej wiedzy.

- [ ] pipeline embeddings dla chunków
- [ ] retrieval top-k z konfiguracji docsetu
- [ ] podstawowy reranking / heurystyki
- [ ] flow Q&A: pytanie -> retrieval -> odpowiedź LLM
- [ ] użycie chunków + skompresowanych artefaktów wiedzy w odpowiedzi

## Milestone 5 — Multi-docset MVP

Cel: stabilna obsługa wielu źródeł dokumentacji.

- [ ] ingest wielu docsetów do jednej bazy
- [ ] śledzenie zmian po commit hash / checksum
- [ ] inkrementalne przetwarzanie tylko zmienionych plików
- [ ] utrzymanie konfiguracji bez hardcode pod pojedynczy docset

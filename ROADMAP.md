# ROADMAP.md - Docemoria

## Milestone 1 — Ingest MVP

Cel: wczytać 1 docset end-to-end.

- wykrywanie docsetu z configu
- skanowanie plików
- parsowanie markdown / tekstu
- chunking
- zapis do DuckDB:
  - sources
  - documents
  - chunks
  - metadata

## Milestone 2 — Generation MVP

Cel: wygenerować pierwsze sensowne materiały edukacyjne.

- provider abstraction
- implementacja startowa dla OpenAI
- base prompt + per-docset prompt
- generowanie:
  - flashcards
  - krótkich notatek do powtórek

## Milestone 3 — Export MVP

Cel: wynik ma być realnie używalny.

- eksport markdown do Obsidiana
- eksport CSV / format pod Anki
- output per docset / run

## Milestone 4 — Retrieval quality + Q&A

Cel: poprawić jakość wyboru materiału do kart i umożliwić sensowne odpowiadanie na pytania po dokumentacji.

- embeddings
- retrieval
- reranking / heurystyki
- lepszy dobór chunków pod typ kart
- podstawowy flow LLM + RAG do odpowiedzi na pytania
- wykorzystanie skompresowanej warstwy wiedzy obok surowych chunków

## Milestone 5 — Multi-docset system

Cel: łatwo podpinać kolejne dokumentacje.

- konfiguracja per source/docset
- różne system prompty
- śledzenie zmian po commit hash / checksum
- wieloźródłowe działanie bez hardcode

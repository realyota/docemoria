# PROJECT.md - Docemoria

## Czym jest Docemoria

Docemoria to ogólny system do zamiany lokalnych dokumentacji technicznych na materiały do nauki:
- karty Anki
- notatki do spaced repetition
- eksport do Obsidiana

## Źródła

- dokumentacje są podpinane jako `git submodules`
- system czyta lokalny checkout repozytoriów
- każdy docset może mieć własną konfigurację i własny system prompt

## Architektura bazowa

- storage: DuckDB
- provider abstraction:
  - embeddings
  - generation
- domyślny start:
  - embeddings: OpenAI text-embedding-3
  - generation: gpt-5.4

## Główna idea

Zamiast budować tylko kolejny ogólny RAG do wszystkiego, Docemoria ma budować pipeline pod naukę i skompresowaną wiedzę:
1. ingest dokumentacji
2. chunking i metadata
3. retrieval / ranking
4. generowanie materiałów edukacyjnych
5. budowa skompresowanej warstwy wiedzy
6. odpowiadanie na pytania przez LLM + RAG
7. eksport do narzędzi używanych do nauki

## Ważne zasady

- prostota MVP > przesadna architektura
- łatwa konfiguracja nowych docsetów
- brak twardego związania z jednym providerem
- per-docset behavior ma być konfigurowalne

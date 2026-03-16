# AGENTS.md - Docemoria

To jest dedykowany workspace projektu `Docemoria`.

## Misja

Budować ogólny system do zamiany lokalnych dokumentacji technicznych na materiały do nauki:
- Anki cards
- spaced repetition notes
- eksport do Obsidiana

## Założenia architektoniczne

- dokumentacje są podpinane jako git submodules
- system czyta lokalny checkout repozytoriów
- storage ma być prosty: DuckDB
- każdy docset może mieć własny system prompt i własną konfigurację
- provider ma być konfigurowalny
- domyślne modele startowe:
  - embeddings: OpenAI text-embedding-3
  - generation: gpt-5.4

## Priorytety

1. prosty, działający MVP
2. łatwa konfiguracja nowych docsetów
3. dobra jakość kart i materiałów do powtórek
4. brak twardego związania z jednym providerem lub jednym docsetem

## Styl pracy

- preferuj konkret nad brainstorming
- projektuj pod praktyczne wdrożenie
- utrzymuj prostą strukturę repo i konfiguracji
- po każdej sensownej zmianie w workspace zrób commit
- po commicie zrób push do repozytorium GitHub `docemoria`
- gdy potrzebne jest uwierzytelnienie do push, użyj tokena z `~/.openclaw/agents/docemoria/.env`

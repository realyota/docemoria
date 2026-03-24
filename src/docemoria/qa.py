from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docemoria.chunk_search import ChunkSectionResult, search_persisted_chunk_sections
from docemoria.config import ConfigError, load_docset_config
from docemoria.providers.openai import OpenAIGenerationProvider
from docemoria.storage import StorageError, open_database

DEFAULT_DB_PATH = "docemoria.db"

def format_context(sections: list[ChunkSectionResult]) -> str:
    """Format retrieved sections into a context string for the LLM."""
    context_parts = []
    for section in sections:
        file_path = section.repo_relative_path
        heading = f"## {section.heading_title}" if section.heading_title else ""
        content = "\n".join(chunk.content for chunk in section.chunks)
        context_parts.append(f"File: {file_path}\n{heading}\n{content}")
    
    return "\n\n---\n\n".join(context_parts)

def build_qa_prompt(query: str, context: str, system_prompt: str = "") -> str:
    """Construct the final RAG prompt."""
    base_prompt = (
        "Use the following documentation snippets to answer the user's question.\n"
        "If the answer is not in the documentation, say you don't know.\n\n"
        f"Documentation:\n{context}\n\n"
        f"Question: {query}\n"
        "Answer:"
    )
    if system_prompt:
        return f"{system_prompt}\n\n{base_prompt}"
    return base_prompt

def perform_qa(
    config_path: Path,
    query: str,
    db_path: Path = Path(DEFAULT_DB_PATH),
    run_id: int | None = None,
    verbose: bool = False
) -> str:
    """Execute the RAG QA flow."""
    # 1. Load config
    config = load_docset_config(config_path)
    
    # 2. Retrieve relevant context
    with open_database(db_path) as conn:
        sections = search_persisted_chunk_sections(
            conn,
            query=query,
            source_id=config.source_id,
            run_id=run_id,
            limit=config.retrieval.top_k,
            max_section_chars=config.retrieval.max_section_chars
        )
    
    if not sections:
        return "No relevant documentation found for the given query."

    context_text = format_context(sections)
    
    # 3. Setup Provider
    gen_config = config.providers.generation
    if not gen_config:
        return "Error: No generation provider configured for this docset."
    
    if gen_config.provider != "openai":
        return f"Error: Provider '{gen_config.provider}' is not supported for QA yet."
    
    provider = OpenAIGenerationProvider(model=gen_config.model)
    
    # 4. Generate Answer
    prompt = build_qa_prompt(query, context_text, system_prompt=config.prompts.system)
    
    if verbose:
        print("\n--- CONTEXT ---")
        print(context_text)
        print("\n--- PROMPT ---")
        print(prompt)
        print("\n--- END PROMPT ---\n")
        
    return provider.generate(prompt)

def main() -> int:
    parser = argparse.ArgumentParser(prog="docemoria-qa")
    parser.add_argument("config_path", help="Path to a docset YAML config")
    parser.add_argument("query", help="Question to ask about the documentation")
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to DuckDB database file (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        help="Optional ingest run_id filter",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print retrieved context and final prompt",
    )
    
    args = parser.parse_args()
    
    try:
        answer = perform_qa(
            Path(args.config_path),
            args.query,
            db_path=Path(args.db_path),
            run_id=args.run_id,
            verbose=args.verbose
        )
        print(f"\nAnswer:\n{answer}")
        return 0
    except (ConfigError, StorageError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

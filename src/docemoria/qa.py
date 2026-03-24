import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent / "src"))

from docemoria.storage import open_database
from docemoria.chunk_search import search_persisted_chunk_sections
from docemoria.providers.openai import OpenAIGenerationProvider

def rag_qa(query: str, db_path: str = "docemoria.db"):
    conn = open_database(db_path)
    
    # 1. Search
    sections = search_persisted_chunk_sections(conn, query=query, limit=3)
    
    if not sections:
        return "No relevant documentation found."
        
    # 2. Build Context
    context_parts = []
    for section in sections:
        file_path = section.repo_relative_path
        heading = f"## {section.heading_title}" if section.heading_title else ""
        content = "\n".join(c.content for c in section.chunks)
        context_parts.append(f"File: {file_path}\n{heading}\n{content}")
    
    context_text = "\n\n---\n\n".join(context_parts)
    
    # 3. Generate Answer
    prompt = f"""Use the following documentation snippets to answer the user's question.
If the answer is not in the documentation, say you don't know.

Documentation:
{context_text}

Question: {query}
Answer:"""

    # For MVP we can just print the prompt or try to use OpenAI if key is present
    print(f"--- PROMPT ---\n{prompt}\n--- END PROMPT ---")
    
    # Simple provider init (expects OPENAI_API_KEY in env)
    try:
        provider = OpenAIGenerationProvider(model="gpt-4o") # Using a real model name
        answer = provider.generate(prompt)
        return answer
    except Exception as e:
        return f"Error generating answer: {e}"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "What is Docemoria?"
        
    print(f"Query: {query}")
    answer = rag_qa(query)
    print(f"\nAnswer:\n{answer}")

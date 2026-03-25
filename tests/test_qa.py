import unittest
from pathlib import Path
from docemoria.config import load_docset_config
from docemoria.qa import format_context, build_qa_prompt
from docemoria.chunk_search import ChunkSectionResult, ChunkContextChunk

class TestQA(unittest.TestCase):
    def test_format_context(self):
        chunk = ChunkContextChunk(
            run_id=1, source_id="src", document_index=0, chunk_index=0,
            repo_relative_path="docs/intro.md", document_title=None,
            heading_title="Intro", heading_path=["Intro"],
            character_count=10, content="Hello world", is_match=True
        )
        section = ChunkSectionResult(
            run_id=1, source_id="src", document_index=0,
            repo_relative_path="docs/intro.md", document_title=None,
            heading_title="Intro", heading_path=["Intro"],
            match_chunk_indexes=[0], chunks=[chunk]
        )
        formatted = format_context([section])
        self.assertIn("File: docs/intro.md", formatted)
        self.assertIn("## Intro", formatted)
        self.assertIn("Hello world", formatted)

    def test_build_qa_prompt(self):
        prompt = build_qa_prompt("What is it?", "Context text")
        self.assertIn("Context text", prompt)
        self.assertIn("What is it?", prompt)
        self.assertIn("Answer:", prompt)

    def test_build_qa_prompt_with_system(self):
        prompt = build_qa_prompt("Q", "C", system_prompt="Be a robot.")
        self.assertTrue(prompt.startswith("Be a robot."))

if __name__ == "__main__":
    unittest.main()

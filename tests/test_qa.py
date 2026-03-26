import unittest

from docemoria.chunk_search import ChunkContextChunk, ChunkSectionResult
from docemoria.qa import build_qa_prompt, format_context


class FakeCursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object]]] = []

    def execute(self, query: str, params: list[object]) -> FakeCursor:
        self.calls.append((query, list(params)))
        normalized = " ".join(query.split())
        if "FROM ingest_runs" in normalized:
            return FakeCursor(("Global summary",))
        if "FROM documents" in normalized:
            return FakeCursor(("Document summary",))
        return FakeCursor(None)


class TestQA(unittest.TestCase):
    def _section(self) -> ChunkSectionResult:
        chunk = ChunkContextChunk(
            run_id=1,
            source_id="src",
            document_index=0,
            chunk_index=0,
            repo_relative_path="docs/intro.md",
            document_title=None,
            heading_title="Intro",
            heading_path=["Intro"],
            character_count=10,
            content="Hello world",
            is_match=True,
        )
        return ChunkSectionResult(
            run_id=1,
            source_id="src",
            document_index=0,
            repo_relative_path="docs/intro.md",
            document_title=None,
            heading_title="Intro",
            heading_path=["Intro"],
            match_chunk_indexes=[0],
            chunks=[chunk],
        )

    def test_format_context_without_summaries(self) -> None:
        formatted = format_context([self._section()])
        self.assertIn("File: docs/intro.md", formatted)
        self.assertIn("## Intro", formatted)
        self.assertIn("Hello world", formatted)
        self.assertNotIn("Global Context:", formatted)
        self.assertNotIn("Summary:", formatted)

    def test_format_context_includes_run_and_document_summaries_when_available(self) -> None:
        connection = FakeConnection()

        formatted = format_context([self._section()], connection=connection, run_id=1)

        self.assertIn("Global Context:\nGlobal summary", formatted)
        self.assertIn("Summary: Document summary", formatted)
        self.assertEqual(len(connection.calls), 2)
        self.assertEqual(connection.calls[0][1], [1])
        self.assertEqual(connection.calls[1][1], [1, 0])

    def test_build_qa_prompt(self) -> None:
        prompt = build_qa_prompt("What is it?", "Context text")
        self.assertIn("Context text", prompt)
        self.assertIn("What is it?", prompt)
        self.assertIn("Answer:", prompt)

    def test_build_qa_prompt_with_system(self) -> None:
        prompt = build_qa_prompt("Q", "C", system_prompt="Be a robot.")
        self.assertTrue(prompt.startswith("Be a robot."))


if __name__ == "__main__":
    unittest.main()

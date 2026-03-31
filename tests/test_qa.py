import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from docemoria.chunk_search import ChunkContextChunk, ChunkSectionResult
from docemoria.qa import build_qa_prompt, format_context, perform_qa


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
    def _section(self, *, run_id: int = 1) -> ChunkSectionResult:
        chunk = ChunkContextChunk(
            run_id=run_id,
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
            run_id=run_id,
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

    def test_format_context_can_be_truncated(self) -> None:
        section = self._section()
        section.chunks[0].content = "A" * 120
        formatted = format_context([section], max_context_chars=80)
        self.assertLessEqual(len(formatted), 80)
        self.assertIn("[Context truncated to keep the prompt compact.]", formatted)

    def test_format_context_includes_run_and_document_summaries_when_available(self) -> None:
        connection = FakeConnection()

        formatted = format_context([self._section()], connection=connection, run_id=1)

        self.assertIn("Global Context:\nGlobal summary", formatted)
        self.assertIn("Summary: Document summary", formatted)
        self.assertEqual(len(connection.calls), 2)
        self.assertEqual(connection.calls[0][1], [1])
        self.assertEqual(connection.calls[1][1], [1, 0])

    def test_perform_qa_defaults_to_latest_successful_run_when_run_id_omitted(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None
        run_id = 9
        section = self._section(run_id=run_id)
        fake_config = SimpleNamespace(
            source_id="sample",
            retrieval=SimpleNamespace(top_k=3, max_section_chars=None),
            providers=SimpleNamespace(generation=SimpleNamespace(provider="openai", model="gpt-5.4")),
            prompts=SimpleNamespace(system="Docset-level guidance.", qa_style="Concise answer style."),
        )

        with patch("docemoria.qa.open_database", return_value=connection), patch(
            "docemoria.qa.load_docset_config",
            return_value=fake_config,
        ) as load_docset_config_mock, patch(
            "docemoria.qa.resolve_latest_successful_run_id",
            return_value=run_id,
        ) as resolve_run_id_mock, patch(
            "docemoria.qa.search_persisted_chunk_sections",
            return_value=[section],
        ) as search_mock, patch(
            "docemoria.qa.format_context",
            return_value="Context",
        ) as format_mock, patch("docemoria.qa.OpenAIGenerationProvider") as provider_class:
            build_prompt_mock = patch("docemoria.qa.build_qa_prompt")
            build_prompt = build_prompt_mock.start()
            build_prompt.return_value = "Built prompt"
            self.addCleanup(build_prompt_mock.stop)

            provider = MagicMock()
            provider.generate.return_value = "answer"
            provider_class.return_value = provider

            answer = perform_qa(Path("configs/docsets/sample.yaml"), "How?", db_path=Path("/tmp/docemoria.duckdb"))

            self.assertEqual(answer, "answer")
            load_docset_config_mock.assert_called_once_with(Path("configs/docsets/sample.yaml"))
            resolve_run_id_mock.assert_called_once_with(connection, source_id="sample")
            search_mock.assert_called_once_with(
                connection,
                query="How?",
                source_id="sample",
                run_id=run_id,
                limit=3,
                max_section_chars=None,
            )
            format_mock.assert_called_once_with(
                [section],
                connection=connection,
                run_id=run_id,
                max_context_chars=None,
            )
            build_prompt.assert_called_once_with(
                "How?",
                "Context",
                system_prompt="Docset-level guidance.",
                qa_style="Concise answer style.",
            )

    def test_perform_qa_can_return_structured_sources(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None
        run_id = 9
        section = self._section(run_id=run_id)
        fake_config = SimpleNamespace(
            source_id="sample",
            retrieval=SimpleNamespace(top_k=3, max_section_chars=None),
            providers=SimpleNamespace(generation=SimpleNamespace(provider="openai", model="gpt-5.4")),
            prompts=SimpleNamespace(system="", qa_style=""),
        )

        with patch("docemoria.qa.open_database", return_value=connection), patch(
            "docemoria.qa.load_docset_config",
            return_value=fake_config,
        ) as load_docset_config_mock, patch(
            "docemoria.qa.resolve_latest_successful_run_id",
            return_value=run_id,
        ) as resolve_run_id_mock, patch(
            "docemoria.qa.search_persisted_chunk_sections",
            return_value=[section],
        ) as search_mock, patch(
            "docemoria.qa.format_context",
            return_value="Context",
        ) as format_mock, patch("docemoria.qa.OpenAIGenerationProvider") as provider_class:
            provider = MagicMock()
            provider.generate.return_value = "answer"
            provider_class.return_value = provider

            answer, sources = perform_qa(
                Path("configs/docsets/sample.yaml"),
                "How?",
                db_path=Path("/tmp/docemoria.duckdb"),
                include_sources=True,
            )

            self.assertEqual(answer, "answer")
            self.assertEqual(
                sources,
                [
                    {
                        "source_id": "src",
                        "document_index": 0,
                        "file": "docs/intro.md",
                        "heading": "Intro",
                        "heading_path": ["Intro"],
                        "match_chunk_indexes": [0],
                    }
                ],
            )
            load_docset_config_mock.assert_called_once_with(Path("configs/docsets/sample.yaml"))
            resolve_run_id_mock.assert_called_once_with(connection, source_id="sample")
            search_mock.assert_called_once_with(
                connection,
                query="How?",
                source_id="sample",
                run_id=run_id,
                limit=3,
                max_section_chars=None,
            )
            format_mock.assert_called_once_with(
                [section],
                connection=connection,
                run_id=run_id,
                max_context_chars=None,
            )

    def test_build_qa_prompt(self) -> None:
        prompt = build_qa_prompt("What is it?", "Context text")
        self.assertIn("Context text", prompt)
        self.assertIn("What is it?", prompt)
        self.assertIn("Answer:", prompt)

    def test_build_qa_prompt_with_system(self) -> None:
        prompt = build_qa_prompt("Q", "C", system_prompt="Be a robot.")
        self.assertTrue(prompt.startswith("Be a robot."))

    def test_build_qa_prompt_with_system_and_qa_style(self) -> None:
        prompt = build_qa_prompt("Q", "C", system_prompt="System guidance.", qa_style="Answer briefly.")
        self.assertIn("System guidance.", prompt)
        self.assertIn("Answer briefly.", prompt)
        self.assertTrue(prompt.index("System guidance.") < prompt.index("Answer briefly."))


if __name__ == "__main__":
    unittest.main()

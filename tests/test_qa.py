import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from docemoria.chunk_search import ChunkContextChunk, ChunkSectionResult
from docemoria.qa import (
    _format_summary_artifacts_context,
    _search_summary_artifacts,
    SummaryArtifact,
    build_qa_prompt,
    format_context,
    format_summary_sources,
    perform_qa,
)
from docemoria.providers.generation import GenerationError


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

    def test_format_summary_artifacts_context_includes_run_and_document_scope(self) -> None:
        context = _format_summary_artifacts_context(
            [
                SummaryArtifact(
                    source_id="sample",
                    run_id=1,
                    scope="run",
                    document_index=None,
                    repo_relative_path=None,
                    document_title=None,
                    summary="Run-level summary",
                ),
                SummaryArtifact(
                    source_id="sample",
                    run_id=1,
                    scope="document",
                    document_index=0,
                    repo_relative_path="docs/intro.md",
                    document_title="Intro",
                    summary="Document summary",
                ),
            ]
        )
        self.assertIn("Run summary", context)
        self.assertIn("Summary artifacts matched in compact knowledge layer", context)
        self.assertIn("Document summary", context)
        self.assertIn("docs/intro.md", context)

    def test_format_summary_sources_keeps_compact_summary_metadata(self) -> None:
        sources = format_summary_sources(
            [
                SummaryArtifact(
                    source_id="sample",
                    run_id=1,
                    scope="run",
                    document_index=None,
                    repo_relative_path=None,
                    document_title=None,
                    summary="Run-level summary",
                ),
                SummaryArtifact(
                    source_id="sample",
                    run_id=1,
                    scope="document",
                    document_index=0,
                    repo_relative_path="docs/intro.md",
                    document_title="Intro",
                    summary="Doc summary",
                ),
            ]
        )
        self.assertEqual(sources[0], {
            "source_id": "sample",
            "document_index": None,
            "file": None,
            "heading": "Run Summary",
            "heading_path": None,
            "match_chunk_indexes": [],
            "summary_scope": "run",
        })
        self.assertEqual(sources[1]["summary_scope"], "document")
        self.assertEqual(sources[1]["file"], "docs/intro.md")

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
            resolve_run_id_mock.assert_called_once_with(connection, source_id="sample")
            self.assertEqual(connection.__enter__.call_count, 1)

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

    def test_perform_qa_falls_back_to_summary_artifacts_when_no_sections_found(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None
        run_id = 9
        fake_config = SimpleNamespace(
            source_id="sample",
            retrieval=SimpleNamespace(top_k=3, max_section_chars=None),
            providers=SimpleNamespace(generation=SimpleNamespace(provider="openai", model="gpt-5.4")),
            prompts=SimpleNamespace(system="", qa_style=""),
        )
        summary_hits = [
            SummaryArtifact(
                source_id="sample",
                run_id=run_id,
                scope="document",
                document_index=0,
                repo_relative_path="docs/overview.md",
                document_title="Overview",
                summary="Overview summary",
            ),
            SummaryArtifact(
                source_id="sample",
                run_id=run_id,
                scope="run",
                document_index=None,
                repo_relative_path=None,
                document_title=None,
                summary="Run summary",
            ),
        ]

        with patch("docemoria.qa.open_database", return_value=connection), patch(
            "docemoria.qa.load_docset_config",
            return_value=fake_config,
        ), patch(
            "docemoria.qa.resolve_latest_successful_run_id",
            return_value=run_id,
        ), patch(
            "docemoria.qa.search_persisted_chunk_sections",
            return_value=[],
        ) as search_mock, patch(
            "docemoria.qa._search_summary_artifacts",
            return_value=summary_hits,
        ) as summary_search_mock, patch(
            "docemoria.qa._format_summary_artifacts_context",
            return_value="summary context",
        ) as format_summary_context_mock, patch(
            "docemoria.qa.format_summary_sources",
            side_effect=format_summary_sources,
        ), patch(
            "docemoria.qa.OpenAIGenerationProvider",
        ) as provider_class:
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
            self.assertEqual(len(sources), 2)
            self.assertEqual(sources[0]["summary_scope"], "document")
            self.assertEqual(sources[1]["summary_scope"], "run")
            search_mock.assert_called_once_with(
                connection,
                query="How?",
                source_id="sample",
                run_id=run_id,
                limit=3,
                max_section_chars=None,
            )
            summary_search_mock.assert_called_once_with(
                connection,
                query="How?",
                source_id="sample",
                run_id=run_id,
                limit=3,
            )
            format_summary_context_mock.assert_called_once_with(
                summary_hits,
                max_context_chars=None,
            )

    def test_search_summary_artifacts_uses_token_overlap_for_multi_word_queries(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchone(self) -> tuple[object, ...] | None:
                return self._rows[0] if self._rows else None

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def execute(self, query: str, params: list[object]) -> FakeCursor:
                normalized = " ".join(query.split())
                if "FROM ingest_runs" in normalized:
                    return FakeCursor([("Global caching overview",)])
                if "FROM documents" in normalized:
                    return FakeCursor(
                        [
                            (
                                9,
                                "sample",
                                0,
                                "docs/latency.md",
                                "Latency",
                                "Latency tuning improves retrieval quality for repeated lookups.",
                            ),
                            (
                                9,
                                "sample",
                                1,
                                "docs/retrieval.md",
                                "Retrieval",
                                "This summary only mentions retrieval behavior.",
                            ),
                            (
                                9,
                                "sample",
                                2,
                                "docs/other.md",
                                "Other",
                                "This summary is unrelated.",
                            ),
                        ]
                    )
                raise AssertionError("unexpected query")

        artifacts = _search_summary_artifacts(
            FakeConnection(),  # type: ignore[arg-type]
            query="retrieval latency",
            source_id="sample",
            run_id=9,
            limit=2,
        )

        self.assertEqual(len(artifacts), 2)
        self.assertEqual([artifact.scope for artifact in artifacts], ["document", "document"])
        self.assertEqual(artifacts[0].repo_relative_path, "docs/latency.md")
        self.assertEqual(artifacts[1].repo_relative_path, "docs/retrieval.md")

    def test_search_summary_artifacts_loads_run_and_document_summary_columns(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchone(self) -> tuple[object, ...] | None:
                return self._rows[0] if self._rows else None

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, list[object]]] = []

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                self.calls.append((query, list(params)))
                normalized = " ".join(query.split())
                if "FROM ingest_runs" in normalized:
                    return FakeCursor([("Run overview summary",)])
                if "FROM documents" in normalized:
                    return FakeCursor(
                        [
                            (
                                9,
                                "sample",
                                0,
                                "docs/overview.md",
                                "Overview",
                                "Document overview summary",
                            )
                        ]
                    )
                raise AssertionError("unexpected query")

        connection = FakeConnection()
        artifacts = _search_summary_artifacts(
            connection,  # type: ignore[arg-type]
            query="overview",
            source_id="sample",
            run_id=9,
            limit=3,
        )
        self.assertEqual(len(artifacts), 2)
        self.assertEqual([artifact.scope for artifact in artifacts], ["run", "document"])
        self.assertIn("summary", artifacts[0].summary.lower())
        self.assertEqual(connection.calls[0][1], [9, "sample"])
        self.assertEqual(connection.calls[1][1], [9, "sample"])
        self.assertIn("summary IS NOT NULL", connection.calls[0][0])
        self.assertIn("FROM documents", connection.calls[1][0])
        self.assertNotIn("strpos", connection.calls[1][0].lower())

    def test_perform_qa_respects_top_k_override(self) -> None:
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
        ), patch(
            "docemoria.qa.resolve_latest_successful_run_id",
            return_value=run_id,
        ), patch(
            "docemoria.qa.search_persisted_chunk_sections",
            return_value=[section],
        ) as search_mock, patch("docemoria.qa.format_context", return_value="Context"), patch(
            "docemoria.qa.OpenAIGenerationProvider"
        ) as provider_class:
            provider = MagicMock()
            provider.generate.return_value = "answer"
            provider_class.return_value = provider

            perform_qa(
                Path("configs/docsets/sample.yaml"),
                "How?",
                db_path=Path("/tmp/docemoria.duckdb"),
                top_k=1,
            )

            search_mock.assert_called_once_with(
                connection,
                query="How?",
                source_id="sample",
                run_id=run_id,
                limit=1,
                max_section_chars=None,
            )

    def test_perform_qa_raises_generation_error_from_provider(self) -> None:
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
        ), patch("docemoria.qa.resolve_latest_successful_run_id", return_value=run_id), patch(
            "docemoria.qa.search_persisted_chunk_sections",
            return_value=[section],
        ), patch("docemoria.qa.format_context", return_value="Context"), patch(
            "docemoria.qa.OpenAIGenerationProvider",
        ) as provider_class:
            provider = MagicMock()
            provider.generate.side_effect = GenerationError("provider unavailable")
            provider_class.return_value = provider

            with self.assertRaisesRegex(GenerationError, "provider unavailable"):
                perform_qa(Path("configs/docsets/sample.yaml"), "How?", db_path=Path("/tmp/docemoria.duckdb"))

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

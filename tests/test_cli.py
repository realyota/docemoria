import contextlib
import io
import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from docemoria import cli
from docemoria.chunk_search import ChunkContextChunk, ChunkContextResult, ChunkSearchResult, ChunkSectionResult
from docemoria.config import DocsetConfig, RetrievalConfig
from docemoria.ingest import IngestResult
from docemoria.ingest_results import IngestRunSummary
from docemoria.providers.generation import GenerationError


class CliTests(unittest.TestCase):
    def test_list_source_files_prints_repo_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repos" / "sample-docs"
            config_path = root / "configs" / "docsets" / "sample.yaml"
            (repo / "docs" / "archive").mkdir(parents=True)
            config_path.parent.mkdir(parents=True)

            (repo / "docs" / "keep.md").write_text("keep", encoding="utf-8")
            (repo / "docs" / "archive" / "skip.md").write_text("skip", encoding="utf-8")

            config_path.write_text(
                "\n".join(
                    [
                        "source_id: sample",
                        "label: Sample",
                        "repo_path: ../../repos/sample-docs",
                        "ingest:",
                        "  include_globs:",
                        "    - docs/**/*.md",
                        "  exclude_globs:",
                        "    - docs/archive/**",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), patch(
                "sys.argv",
                ["docemoria", "list-source-files", str(config_path)],
            ):
                exit_code = cli.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "docs/keep.md\n")

    def test_preview_documents_prints_metadata_without_content_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repos" / "sample-docs"
            config_path = root / "configs" / "docsets" / "sample.yaml"
            (repo / "docs").mkdir(parents=True)
            config_path.parent.mkdir(parents=True)

            (repo / "docs" / "intro.md").write_text("# Intro\nBody\n", encoding="utf-8")
            (repo / "notes.txt").write_text("Remember this.\n", encoding="utf-8")

            config_path.write_text(
                "source_id: sample\nlabel: Sample\nrepo_path: ../../repos/sample-docs\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), patch(
                "sys.argv",
                ["docemoria", "preview-documents", str(config_path)],
            ):
                exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["source_id"], "sample")
            self.assertEqual(payload["document_count"], 2)
            self.assertEqual(payload["documents"][0]["repo_relative_path"], "docs/intro.md")
            self.assertEqual(payload["documents"][0]["file_type"], "markdown")
            self.assertEqual(payload["documents"][0]["document_title"], "Intro")
            self.assertEqual(payload["documents"][0]["character_count"], len("# Intro\nBody\n"))
            self.assertNotIn("content", payload["documents"][0])

    def test_preview_documents_can_include_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repos" / "sample-docs"
            config_path = root / "configs" / "docsets" / "sample.yaml"
            (repo / "docs").mkdir(parents=True)
            config_path.parent.mkdir(parents=True)

            (repo / "docs" / "intro.md").write_text("# Intro\n", encoding="utf-8")

            config_path.write_text(
                "source_id: sample\nlabel: Sample\nrepo_path: ../../repos/sample-docs\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), patch(
                "sys.argv",
                ["docemoria", "preview-documents", "--include-content", str(config_path)],
            ):
                exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["documents"][0]["document_title"], "Intro")
            self.assertEqual(payload["documents"][0]["content"], "# Intro\n")

    def test_preview_chunks_prints_chunked_document_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repos" / "sample-docs"
            config_path = root / "configs" / "docsets" / "sample.yaml"
            (repo / "docs").mkdir(parents=True)
            config_path.parent.mkdir(parents=True)

            (repo / "docs" / "intro.md").write_text("abcdefghij", encoding="utf-8")

            config_path.write_text(
                "\n".join(
                    [
                        "source_id: sample",
                        "label: Sample",
                        "repo_path: ../../repos/sample-docs",
                        "chunking:",
                        "  max_chars: 5",
                        "  overlap_chars: 2",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), patch(
                "sys.argv",
                ["docemoria", "preview-chunks", str(config_path)],
            ):
                exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["source_id"], "sample")
            self.assertEqual(payload["document_count"], 1)
            self.assertEqual(payload["chunk_count"], 3)
            self.assertEqual(payload["chunking"]["max_chars"], 5)
            self.assertEqual(payload["chunking"]["overlap_chars"], 2)
            self.assertEqual(
                [
                    (
                        chunk["document_index"],
                        chunk["chunk_index"],
                        chunk["start_char"],
                        chunk["end_char"],
                        chunk["document_title"],
                        chunk["heading_title"],
                        chunk["heading_level"],
                        chunk["heading_path"],
                        chunk["content"],
                    )
                    for chunk in payload["chunks"]
                ],
                [
                    (0, 0, 0, 5, None, None, None, None, "abcde"),
                    (0, 1, 3, 8, None, None, None, None, "defgh"),
                    (0, 2, 6, 10, None, None, None, None, "ghij"),
                ],
            )

    def test_preview_chunks_uses_markdown_section_strategy_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repos" / "sample-docs"
            config_path = root / "configs" / "docsets" / "sample.yaml"
            (repo / "docs").mkdir(parents=True)
            config_path.parent.mkdir(parents=True)

            content = "# Intro\nalpha\n## Details\ngamma\n"
            (repo / "docs" / "intro.md").write_text(content, encoding="utf-8")

            config_path.write_text(
                "\n".join(
                    [
                        "source_id: sample",
                        "label: Sample",
                        "repo_path: ../../repos/sample-docs",
                        "chunking:",
                        "  strategy: markdown-sections",
                        "  max_chars: 100",
                        "  overlap_chars: 10",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), patch(
                "sys.argv",
                ["docemoria", "preview-chunks", str(config_path)],
            ):
                exit_code = cli.main()

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["chunking"]["strategy"], "markdown-sections")
            self.assertEqual(payload["chunk_count"], 2)
            self.assertEqual(
                [
                    (
                        chunk["chunk_index"],
                        chunk["start_char"],
                        chunk["end_char"],
                        chunk["document_title"],
                        chunk["heading_title"],
                        chunk["heading_level"],
                        chunk["heading_path"],
                        chunk["content"],
                    )
                    for chunk in payload["chunks"]
                ],
                [
                    (0, 0, content.index("## Details\n"), "Intro", "Intro", 1, ["Intro"], "# Intro\nalpha\n"),
                    (
                        1,
                        content.index("## Details\n"),
                        len(content),
                        "Intro",
                        "Details",
                        2,
                        ["Intro", "Details"],
                        "## Details\ngamma\n",
                    ),
                ],
            )

    def test_init_db_initializes_schema_and_prints_summary(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch("sys.argv", ["docemoria", "init-db", "./tmp/docemoria.duckdb"]), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch("docemoria.cli.initialize_schema") as initialize_schema_mock:
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        open_database_mock.assert_called_once()
        initialize_schema_mock.assert_called_once_with(connection)
        self.assertTrue(payload["schema_initialized"])
        self.assertEqual(payload["tables"], ["ingest_runs", "sources", "documents", "chunks"])
        self.assertTrue(payload["db_path"].endswith("tmp/docemoria.duckdb"))

    def test_ingest_docset_prints_summary_json(self) -> None:
        config_path = Path("configs/docsets/example.yaml")
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            ["docemoria", "ingest-docset", str(config_path), "--db-path", "./tmp/docemoria.duckdb"],
        ), patch(
            "docemoria.cli.ingest_docset",
            return_value=IngestResult(
                run_id=7,
                source_id="example",
                document_count=2,
                chunk_count=5,
                db_path="/tmp/docemoria.duckdb",
                status="success",
            ),
        ) as ingest_docset_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        ingest_docset_mock.assert_called_once_with(
            config_path,
            db_path=Path("./tmp/docemoria.duckdb"),
        )
        self.assertEqual(
            payload,
            {
                "run_id": 7,
                "source_id": "example",
                "document_count": 2,
                "chunk_count": 5,
                "db_path": "/tmp/docemoria.duckdb",
                "status": "success",
            },
        )

    def test_show_ingest_run_prints_latest_summary_json_by_default(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            ["docemoria", "show-ingest-run", "--db-path", "./tmp/docemoria.duckdb"],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.fetch_ingest_run_summary",
            return_value=IngestRunSummary(
                run_id=11,
                source_id="sample",
                status="success",
                started_at="2026-03-20 15:58:01",
                finished_at="2026-03-20 15:58:02",
                document_count=2,
                chunk_count=5,
                persisted_document_count=2,
                persisted_chunk_count=5,
                persisted_chunk_heading_path_count=4,
                error_message=None,
            ),
        ) as fetch_summary_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        fetch_summary_mock.assert_called_once_with(connection, run_id=None)
        self.assertEqual(payload["run_id"], 11)
        self.assertEqual(payload["persisted_document_count"], 2)
        self.assertEqual(payload["persisted_chunk_count"], 5)
        self.assertEqual(payload["persisted_chunk_heading_path_count"], 4)

    def test_show_ingest_run_passes_explicit_run_id(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            ["docemoria", "show-ingest-run", "--db-path", "./tmp/docemoria.duckdb", "--run-id", "7"],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ), patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.fetch_ingest_run_summary",
            return_value=IngestRunSummary(
                run_id=7,
                source_id="sample",
                status="success",
                started_at="2026-03-20 15:58:01",
                finished_at="2026-03-20 15:58:02",
                document_count=2,
                chunk_count=5,
                persisted_document_count=2,
                persisted_chunk_count=5,
                persisted_chunk_heading_path_count=3,
                error_message=None,
            ),
        ) as fetch_summary_mock:
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        initialize_schema_mock.assert_called_once_with(connection)
        fetch_summary_mock.assert_called_once_with(connection, run_id=7)
        self.assertEqual(payload["run_id"], 7)

    def test_summarize_run_executes_summarization(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None
        config_path = Path("configs/docsets/sample.yaml")
        config = DocsetConfig(
            source_id="sample",
            label="Sample Docs",
            repo_path="../../repos/sample-docs",
            config_path=str(config_path),
        )

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "summarize-run",
                str(config_path),
                "11",
                "--db-path",
                "./tmp/docemoria.duckdb",
            ],
        ), patch(
            "docemoria.cli.load_docset_config",
            return_value=config,
        ) as load_docset_config_mock, patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.summarize_run",
        ) as summarize_run_mock:
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        load_docset_config_mock.assert_called_once_with(config_path)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        summarize_run_mock.assert_called_once_with(connection, config, run_id=11, verbose=False)

    def test_list_ingest_runs_prints_compact_json_and_respects_limit(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            ["docemoria", "list-ingest-runs", "--db-path", "./tmp/docemoria.duckdb", "--limit", "3"],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.fetch_recent_ingest_runs",
            return_value=[
                IngestRunSummary(
                    run_id=12,
                    source_id="sample-a",
                    status="success",
                    started_at="2026-03-20 15:58:03",
                    finished_at="2026-03-20 15:58:06",
                    document_count=4,
                    chunk_count=9,
                    persisted_document_count=4,
                    persisted_chunk_count=9,
                    persisted_chunk_heading_path_count=8,
                    error_message=None,
                ),
                IngestRunSummary(
                    run_id=11,
                    source_id="sample-b",
                    status="failed",
                    started_at="2026-03-20 15:58:01",
                    finished_at="2026-03-20 15:58:02",
                    document_count=3,
                    chunk_count=0,
                    persisted_document_count=2,
                    persisted_chunk_count=0,
                    persisted_chunk_heading_path_count=0,
                    error_message="boom",
                ),
            ],
        ) as fetch_recent_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        fetch_recent_mock.assert_called_once_with(connection, limit=3)
        self.assertEqual([entry["run_id"] for entry in payload], [12, 11])
        self.assertEqual(payload[1]["error_message"], "boom")

    def test_search_chunks_prints_compact_json_and_passes_filters(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "search-chunks",
                "needle",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--source-id",
                "sample",
                "--run-id",
                "7",
                "--limit",
                "2",
            ],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.search_persisted_chunks",
            return_value=[
                ChunkSearchResult(
                    run_id=7,
                    source_id="sample",
                    document_index=0,
                    chunk_index=1,
                    repo_relative_path="docs/intro.md",
                    document_title="Intro",
                    heading_title="Details",
                    heading_path=["Intro", "Details"],
                    character_count=42,
                    content="Needle content",
                )
            ],
        ) as search_chunks_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        search_chunks_mock.assert_called_once_with(
            connection,
            query="needle",
            source_id="sample",
            run_id=7,
            limit=2,
        )
        self.assertEqual(payload["query"], "needle")
        self.assertEqual(payload["filters"], {"source_id": "sample", "run_id": 7, "limit": 2})
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["matches"][0]["heading_path"], ["Intro", "Details"])

    def test_search_context_prints_grouped_context_json_and_passes_window(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "search-context",
                "needle",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--source-id",
                "sample",
                "--run-id",
                "7",
                "--limit",
                "2",
                "--before",
                "2",
                "--after",
                "1",
            ],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.search_persisted_chunk_context",
            return_value=[
                ChunkContextResult(
                    run_id=7,
                    source_id="sample",
                    document_index=0,
                    repo_relative_path="docs/intro.md",
                    document_title="Intro",
                    match_chunk_indexes=[3],
                    chunks=[
                        ChunkContextChunk(
                            run_id=7,
                            source_id="sample",
                            document_index=0,
                            chunk_index=1,
                            repo_relative_path="docs/intro.md",
                            document_title="Intro",
                            heading_title="Details",
                            heading_path=["Intro", "Details"],
                            character_count=40,
                            content="context before",
                            is_match=False,
                        ),
                        ChunkContextChunk(
                            run_id=7,
                            source_id="sample",
                            document_index=0,
                            chunk_index=3,
                            repo_relative_path="docs/intro.md",
                            document_title="Intro",
                            heading_title="Details",
                            heading_path=["Intro", "Details"],
                            character_count=42,
                            content="Needle content",
                            is_match=True,
                        ),
                    ],
                )
            ],
        ) as search_context_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        search_context_mock.assert_called_once_with(
            connection,
            query="needle",
            source_id="sample",
            run_id=7,
            limit=2,
            sibling_chunks_before=2,
            sibling_chunks_after=1,
        )
        self.assertEqual(payload["query"], "needle")
        self.assertEqual(payload["filters"], {"source_id": "sample", "run_id": 7, "limit": 2})
        self.assertEqual(payload["context_window"], {"before": 2, "after": 1})
        self.assertEqual(payload["group_count"], 1)
        self.assertEqual(payload["groups"][0]["match_chunk_indexes"], [3])
        self.assertEqual(payload["groups"][0]["chunk_count"], 2)
        self.assertEqual(payload["groups"][0]["chunks"][0]["is_match"], False)
        self.assertEqual(payload["groups"][0]["chunks"][1]["is_match"], True)

    def test_search_sections_prints_grouped_section_json_and_passes_filters(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "search-sections",
                "needle",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--source-id",
                "sample",
                "--run-id",
                "7",
                "--limit",
                "2",
            ],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.search_persisted_chunk_sections",
            return_value=[
                ChunkSectionResult(
                    run_id=7,
                    source_id="sample",
                    document_index=0,
                    repo_relative_path="docs/intro.md",
                    document_title="Intro",
                    heading_title="Details",
                    heading_path=["Intro", "Details"],
                    match_chunk_indexes=[1, 2],
                    chunks=[
                        ChunkContextChunk(
                            run_id=7,
                            source_id="sample",
                            document_index=0,
                            chunk_index=0,
                            repo_relative_path="docs/intro.md",
                            document_title="Intro",
                            heading_title="Details",
                            heading_path=["Intro", "Details"],
                            character_count=25,
                            content="Section context",
                            is_match=False,
                        ),
                        ChunkContextChunk(
                            run_id=7,
                            source_id="sample",
                            document_index=0,
                            chunk_index=1,
                            repo_relative_path="docs/intro.md",
                            document_title="Intro",
                            heading_title="Details",
                            heading_path=["Intro", "Details"],
                            character_count=35,
                            content="Needle content a",
                            is_match=True,
                        ),
                        ChunkContextChunk(
                            run_id=7,
                            source_id="sample",
                            document_index=0,
                            chunk_index=2,
                            repo_relative_path="docs/intro.md",
                            document_title="Intro",
                            heading_title="Details",
                            heading_path=["Intro", "Details"],
                            character_count=30,
                            content="Needle content b",
                            is_match=True,
                        ),
                    ],
                )
            ],
        ) as search_sections_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        search_sections_mock.assert_called_once_with(
            connection,
            query="needle",
            source_id="sample",
            run_id=7,
            limit=2,
            max_section_chars=None,
        )
        self.assertEqual(payload["query"], "needle")
        self.assertEqual(
            payload["filters"],
            {"source_id": "sample", "run_id": 7, "limit": 2, "max_section_chars": None},
        )
        self.assertEqual(payload["group_count"], 1)
        self.assertEqual(payload["groups"][0]["heading_path"], ["Intro", "Details"])
        self.assertEqual(payload["groups"][0]["match_chunk_indexes"], [1, 2])
        self.assertEqual(payload["groups"][0]["chunk_count"], 3)
        self.assertEqual(payload["groups"][0]["chunks"][0]["chunk_index"], 0)
        self.assertFalse(payload["groups"][0]["chunks"][0]["is_match"])
        self.assertEqual(payload["groups"][0]["chunks"][1]["chunk_index"], 1)
        self.assertTrue(payload["groups"][0]["chunks"][1]["is_match"])
        self.assertEqual(payload["groups"][0]["chunks"][2]["chunk_index"], 2)
        self.assertTrue(payload["groups"][0]["chunks"][2]["is_match"])

    def test_search_sections_passes_max_section_chars_when_provided(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "search-sections",
                "needle",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--limit",
                "2",
                "--max-section-chars",
                "120",
            ],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ), patch(
            "docemoria.cli.initialize_schema",
        ), patch(
            "docemoria.cli.search_persisted_chunk_sections",
            return_value=[],
        ) as search_sections_mock:
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        search_sections_mock.assert_called_once_with(
            connection,
            query="needle",
            source_id=None,
            run_id=None,
            limit=2,
            max_section_chars=120,
        )
        self.assertEqual(
            payload["filters"],
            {"source_id": None, "run_id": None, "limit": 2, "max_section_chars": 120},
        )

    def test_search_sections_rejects_non_positive_max_section_chars(self) -> None:
        stderr = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stderr(stderr), patch(
            "sys.argv",
            [
                "docemoria",
                "search-sections",
                "needle",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--max-section-chars",
                "0",
            ],
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ), patch(
            "docemoria.cli.initialize_schema",
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("max_section_chars must be greater than 0 when provided", stderr.getvalue())

    def test_retrieve_context_loads_docset_defaults_and_returns_section_groups(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None
        config_path = Path("configs/docsets/sample.yaml")

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "retrieve-context",
                str(config_path),
                "needle",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--run-id",
                "7",
            ],
        ), patch(
            "docemoria.cli.load_docset_config",
            return_value=DocsetConfig(
                source_id="sample",
                label="Sample Docs",
                repo_path="../../repos/sample-docs",
                retrieval=RetrievalConfig(top_k=9, rerank=True, max_section_chars=120),
                config_path=str(config_path),
            ),
        ) as load_docset_config_mock, patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.search_persisted_chunk_sections",
            return_value=[
                ChunkSectionResult(
                    run_id=7,
                    source_id="sample",
                    document_index=0,
                    repo_relative_path="docs/intro.md",
                    document_title="Intro",
                    heading_title="Details",
                    heading_path=["Intro", "Details"],
                    match_chunk_indexes=[1],
                    chunks=[
                        ChunkContextChunk(
                            run_id=7,
                            source_id="sample",
                            document_index=0,
                            chunk_index=1,
                            repo_relative_path="docs/intro.md",
                            document_title="Intro",
                            heading_title="Details",
                            heading_path=["Intro", "Details"],
                            character_count=35,
                            content="Needle content",
                            is_match=True,
                        ),
                    ],
                )
            ],
        ) as search_sections_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        load_docset_config_mock.assert_called_once_with(config_path)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        search_sections_mock.assert_called_once_with(
            connection,
            query="needle",
            source_id="sample",
            run_id=7,
            limit=9,
            max_section_chars=120,
        )
        self.assertEqual(payload["query"], "needle")
        self.assertEqual(
            payload["docset"],
            {
                "config_path": str(config_path),
                "source_id": "sample",
                "label": "Sample Docs",
            },
        )
        self.assertEqual(payload["filters"], {"source_id": "sample", "run_id": 7, "limit": 9, "max_section_chars": 120})
        self.assertEqual(payload["group_count"], 1)
        self.assertEqual(payload["groups"][0]["heading_path"], ["Intro", "Details"])

    def test_retrieve_neighbors_loads_docset_defaults_and_returns_context_groups(self) -> None:
        stdout = io.StringIO()
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None
        config_path = Path("configs/docsets/sample.yaml")

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "retrieve-neighbors",
                str(config_path),
                "needle",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--run-id",
                "7",
            ],
        ), patch(
            "docemoria.cli.load_docset_config",
            return_value=DocsetConfig(
                source_id="sample",
                label="Sample Docs",
                repo_path="../../repos/sample-docs",
                retrieval=RetrievalConfig(
                    top_k=9,
                    rerank=True,
                    max_section_chars=None,
                    context_before_chunks=0,
                    context_after_chunks=2,
                ),
                config_path=str(config_path),
            ),
        ) as load_docset_config_mock, patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema",
        ) as initialize_schema_mock, patch(
            "docemoria.cli.search_persisted_chunk_context",
            return_value=[
                ChunkContextResult(
                    run_id=7,
                    source_id="sample",
                    document_index=0,
                    repo_relative_path="docs/intro.md",
                    document_title="Intro",
                    match_chunk_indexes=[1],
                    chunks=[
                        ChunkContextChunk(
                            run_id=7,
                            source_id="sample",
                            document_index=0,
                            chunk_index=1,
                            repo_relative_path="docs/intro.md",
                            document_title="Intro",
                            heading_title="Details",
                            heading_path=["Intro", "Details"],
                            character_count=35,
                            content="Needle content",
                            is_match=True,
                        ),
                    ],
                )
            ],
        ) as search_context_mock:
            exit_code = cli.main()

        rendered = stdout.getvalue().strip()
        payload = json.loads(rendered)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("\n", rendered)
        load_docset_config_mock.assert_called_once_with(config_path)
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        search_context_mock.assert_called_once_with(
            connection,
            query="needle",
            source_id="sample",
            run_id=7,
            limit=9,
            sibling_chunks_before=0,
            sibling_chunks_after=2,
        )
        self.assertEqual(payload["query"], "needle")
        self.assertEqual(
            payload["docset"],
            {
                "config_path": str(config_path),
                "source_id": "sample",
                "label": "Sample Docs",
            },
        )
        self.assertEqual(payload["filters"], {"source_id": "sample", "run_id": 7, "limit": 9})
        self.assertEqual(payload["context_window"], {"before": 0, "after": 2})
        self.assertEqual(payload["group_count"], 1)
        self.assertEqual(payload["groups"][0]["match_chunk_indexes"], [1])

    def test_ask_prints_plain_answer_by_default(self) -> None:
        stdout = io.StringIO()
        config_path = Path("configs/docsets/sample.yaml")

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "ask",
                str(config_path),
                "What?",
                "--db-path",
                "./tmp/docemoria.duckdb",
            ],
        ), patch(
            "docemoria.cli.perform_qa",
            return_value="answer",
        ) as perform_qa_mock:
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "answer")
        perform_qa_mock.assert_called_once_with(
            config_path,
            "What?",
            db_path=Path("./tmp/docemoria.duckdb"),
            run_id=None,
            max_context_chars=None,
            verbose=False,
            include_sources=False,
        )

    def test_ask_passes_top_k_override(self) -> None:
        stdout = io.StringIO()
        config_path = Path("configs/docsets/sample.yaml")

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "ask",
                str(config_path),
                "What?",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--top-k",
                "5",
            ],
        ), patch(
            "docemoria.cli.perform_qa",
            return_value="answer",
        ) as perform_qa_mock:
            exit_code = cli.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "answer")
        perform_qa_mock.assert_called_once_with(
            config_path,
            "What?",
            db_path=Path("./tmp/docemoria.duckdb"),
            run_id=None,
            max_context_chars=None,
            top_k=5,
            verbose=False,
            include_sources=False,
        )

    def test_ask_prints_answer_and_structured_sources_with_flag(self) -> None:
        stdout = io.StringIO()
        config_path = Path("configs/docsets/sample.yaml")
        sources = [
            {
                "source_id": "src",
                "document_index": 0,
                "file": "docs/intro.md",
                "heading": "Intro",
                "heading_path": ["Intro"],
                "match_chunk_indexes": [0],
            }
        ]

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "ask",
                str(config_path),
                "What?",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--with-sources",
            ],
        ), patch(
            "docemoria.cli.perform_qa",
            return_value=("answer", sources),
        ) as perform_qa_mock:
            exit_code = cli.main()

        lines = stdout.getvalue().splitlines()
        self.assertEqual(exit_code, 0)
        self.assertEqual(lines[0], "answer")
        self.assertEqual(json.loads(lines[1]), {"sources": sources})
        perform_qa_mock.assert_called_once_with(
            config_path,
            "What?",
            db_path=Path("./tmp/docemoria.duckdb"),
            run_id=None,
            max_context_chars=None,
            verbose=False,
            include_sources=True,
        )

    def test_ask_prints_single_json_object_without_sources_with_flag(self) -> None:
        stdout = io.StringIO()
        config_path = Path("configs/docsets/sample.yaml")

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "ask",
                str(config_path),
                "What?",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--json",
                "--run-id",
                "7",
            ],
        ), patch(
            "docemoria.cli.load_docset_config",
            return_value=SimpleNamespace(source_id="sample", label="Sample Docs"),
        ), patch(
            "docemoria.cli.perform_qa",
            return_value="answer",
        ) as perform_qa_mock:
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload,
            {
                "answer": "answer",
                "metadata": {"run_id": 7, "docset": {"source_id": "sample", "label": "Sample Docs"}},
            },
        )
        perform_qa_mock.assert_called_once_with(
            config_path,
            "What?",
            db_path=Path("./tmp/docemoria.duckdb"),
            run_id=7,
            max_context_chars=None,
            verbose=False,
            include_sources=False,
        )

    def test_ask_prints_single_json_object_with_structured_sources_with_flag(self) -> None:
        stdout = io.StringIO()
        config_path = Path("configs/docsets/sample.yaml")
        sources = [
            {
                "source_id": "src",
                "document_index": 0,
                "file": "docs/intro.md",
                "heading": "Intro",
                "heading_path": ["Intro"],
                "match_chunk_indexes": [0],
            }
        ]

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "ask",
                str(config_path),
                "What?",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--with-sources",
                "--json",
                "--run-id",
                "7",
            ],
        ), patch(
            "docemoria.cli.load_docset_config",
            return_value=SimpleNamespace(source_id="sample", label="Sample Docs"),
        ), patch(
            "docemoria.cli.perform_qa",
            return_value=("answer", sources),
        ) as perform_qa_mock:
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload,
            {
                "answer": "answer",
                "sources": sources,
                "metadata": {"run_id": 7, "docset": {"source_id": "sample", "label": "Sample Docs"}},
            },
        )
        perform_qa_mock.assert_called_once_with(
            config_path,
            "What?",
            db_path=Path("./tmp/docemoria.duckdb"),
            run_id=7,
            max_context_chars=None,
            verbose=False,
            include_sources=True,
        )

    def test_ask_json_resolves_latest_run_id_for_metadata(self) -> None:
        stdout = io.StringIO()
        config_path = Path("configs/docsets/sample.yaml")
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = None

        with contextlib.redirect_stdout(stdout), patch(
            "sys.argv",
            [
                "docemoria",
                "ask",
                str(config_path),
                "What?",
                "--db-path",
                "./tmp/docemoria.duckdb",
                "--json",
            ],
        ), patch(
            "docemoria.cli.load_docset_config",
            return_value=SimpleNamespace(source_id="sample", label="Sample Docs"),
        ), patch(
            "docemoria.cli.open_database",
            return_value=connection,
        ) as open_database_mock, patch(
            "docemoria.cli.initialize_schema"
        ) as initialize_schema_mock, patch(
            "docemoria.cli.resolve_latest_successful_run_id",
            return_value=42,
        ) as resolve_run_id_mock, patch(
            "docemoria.cli.perform_qa",
            return_value="answer",
        ) as perform_qa_mock:
            exit_code = cli.main()

        payload = json.loads(stdout.getvalue().strip())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload,
            {
                "answer": "answer",
                "metadata": {"run_id": 42, "docset": {"source_id": "sample", "label": "Sample Docs"}},
            },
        )
        open_database_mock.assert_called_once_with(Path("./tmp/docemoria.duckdb"))
        initialize_schema_mock.assert_called_once_with(connection)
        resolve_run_id_mock.assert_called_once_with(connection, source_id="sample")
        perform_qa_mock.assert_called_once_with(
            config_path,
            "What?",
            db_path=Path("./tmp/docemoria.duckdb"),
            run_id=42,
            max_context_chars=None,
            verbose=False,
            include_sources=False,
        )

    def test_ask_prints_generation_error_message_on_provider_failure(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        config_path = Path("configs/docemoria/sample.yaml")

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), patch(
            "sys.argv",
            [
                "docemoria",
                "ask",
                str(config_path),
                "What?",
                "--db-path",
                "./tmp/docemoria.duckdb",
            ],
        ), patch(
            "docemoria.cli.perform_qa",
            side_effect=GenerationError("OpenAI unavailable"),
        ) as perform_qa_mock:
            exit_code = cli.main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue().strip(), "Generation failed: OpenAI unavailable")
        perform_qa_mock.assert_called_once_with(
            config_path,
            "What?",
            db_path=Path("./tmp/docemoria.duckdb"),
            run_id=None,
            max_context_chars=None,
            verbose=False,
            include_sources=False,
        )


if __name__ == "__main__":
    unittest.main()

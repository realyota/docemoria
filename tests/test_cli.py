import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from docemoria import cli
from docemoria.ingest import IngestResult
from docemoria.ingest_results import IngestRunSummary


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
                        chunk["heading_title"],
                        chunk["heading_level"],
                        chunk["heading_path"],
                        chunk["content"],
                    )
                    for chunk in payload["chunks"]
                ],
                [
                    (0, 0, 0, 5, None, None, None, "abcde"),
                    (0, 1, 3, 8, None, None, None, "defgh"),
                    (0, 2, 6, 10, None, None, None, "ghij"),
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
                        chunk["heading_title"],
                        chunk["heading_level"],
                        chunk["heading_path"],
                        chunk["content"],
                    )
                    for chunk in payload["chunks"]
                ],
                [
                    (0, 0, content.index("## Details\n"), "Intro", 1, ["Intro"], "# Intro\nalpha\n"),
                    (
                        1,
                        content.index("## Details\n"),
                        len(content),
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


if __name__ == "__main__":
    unittest.main()

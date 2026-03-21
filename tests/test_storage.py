import importlib.util
import tempfile
import unittest
from pathlib import Path

import docemoria

from docemoria.ingest import ingest_docset
from docemoria.ingest_results import fetch_ingest_run_summary, fetch_recent_ingest_runs
from docemoria.storage import StorageError, initialize_schema, open_database

DUCKDB_AVAILABLE = importlib.util.find_spec("duckdb") is not None


class StorageApiSurfaceTests(unittest.TestCase):
    def test_package_exports_storage_bootstrap_api(self) -> None:
        self.assertIs(docemoria.open_database, open_database)
        self.assertIs(docemoria.initialize_schema, initialize_schema)
        self.assertIs(docemoria.StorageError, StorageError)

    def test_initialize_schema_requires_connection(self) -> None:
        with self.assertRaisesRegex(StorageError, "DuckDB connection is required"):
            initialize_schema(None)  # type: ignore[arg-type]

    def test_fetch_ingest_run_summary_maps_row_to_dataclass(self) -> None:
        class FakeCursor:
            def __init__(self, row: tuple[object, ...] | None) -> None:
                self._row = row

            def fetchone(self) -> tuple[object, ...] | None:
                return self._row

            def fetchall(self) -> list[tuple[object, ...]]:
                return [] if self._row is None else [self._row]

        class FakeConnection:
            def __init__(self, row: tuple[object, ...] | None) -> None:
                self.row = row
                self.calls: list[tuple[str, list[int] | None]] = []

            def execute(self, query: str, params: list[int] | None = None) -> FakeCursor:
                self.calls.append((query, params))
                return FakeCursor(self.row)

        connection = FakeConnection(
            (
                7,
                "sample",
                "success",
                "2026-03-20 15:58:01",
                "2026-03-20 15:58:02",
                2,
                5,
                2,
                5,
                4,
                None,
            )
        )
        summary = fetch_ingest_run_summary(connection, run_id=7)  # type: ignore[arg-type]

        self.assertEqual(summary.run_id, 7)
        self.assertEqual(summary.source_id, "sample")
        self.assertEqual(summary.persisted_document_count, 2)
        self.assertEqual(summary.persisted_chunk_count, 5)
        self.assertEqual(summary.persisted_chunk_heading_path_count, 4)
        self.assertEqual(connection.calls[0][1], [7, 1])

    def test_fetch_ingest_run_summary_raises_when_no_runs_exist(self) -> None:
        class FakeCursor:
            def fetchone(self) -> tuple[object, ...] | None:
                return None

            def fetchall(self) -> list[tuple[object, ...]]:
                return []

        class FakeConnection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, list[int] | None]] = []

            def execute(self, query: str, params: list[int] | None = None) -> FakeCursor:
                self.calls.append((query, params))
                return FakeCursor()

        connection = FakeConnection()
        with self.assertRaisesRegex(StorageError, "No ingest runs found in DuckDB"):
            fetch_ingest_run_summary(connection)  # type: ignore[arg-type]
        self.assertEqual(connection.calls[0][1], [1])

    def test_fetch_recent_ingest_runs_maps_rows_and_passes_limit(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self.rows = rows
                self.calls: list[tuple[str, list[int] | None]] = []

            def execute(self, query: str, params: list[int] | None = None) -> FakeCursor:
                self.calls.append((query, params))
                return FakeCursor(self.rows)

        connection = FakeConnection(
            [
                (
                    12,
                    "sample-a",
                    "success",
                    "2026-03-20 15:58:03",
                    "2026-03-20 15:58:06",
                    4,
                    9,
                    4,
                    9,
                    8,
                    None,
                ),
                (
                    11,
                    "sample-b",
                    "failed",
                    "2026-03-20 15:58:01",
                    "2026-03-20 15:58:02",
                    3,
                    0,
                    2,
                    0,
                    0,
                    "boom",
                ),
            ]
        )

        summaries = fetch_recent_ingest_runs(connection, limit=2)  # type: ignore[arg-type]
        self.assertEqual([summary.run_id for summary in summaries], [12, 11])
        self.assertEqual(summaries[1].error_message, "boom")
        self.assertEqual(connection.calls[0][1], [2])

    def test_fetch_recent_ingest_runs_requires_positive_limit(self) -> None:
        class FakeCursor:
            def fetchall(self) -> list[tuple[object, ...]]:
                return []

        class FakeConnection:
            def execute(self, query: str, params: list[int] | None = None) -> FakeCursor:
                return FakeCursor()

        with self.assertRaisesRegex(StorageError, "Limit must be greater than 0"):
            fetch_recent_ingest_runs(FakeConnection(), limit=0)  # type: ignore[arg-type]


@unittest.skipUnless(DUCKDB_AVAILABLE, "duckdb is required for storage tests")
class StorageBootstrapTests(unittest.TestCase):
    def test_open_database_and_initialize_schema_create_expected_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "docemoria.duckdb"
            connection = open_database(db_path)
            self.addCleanup(connection.close)

            initialize_schema(connection)

            table_names = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                    """
                ).fetchall()
            }
            self.assertTrue({"ingest_runs", "sources", "documents", "chunks"}.issubset(table_names))
            self.assertTrue(db_path.exists())

    def test_initialize_schema_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "docemoria.duckdb"
            connection = open_database(db_path)
            self.addCleanup(connection.close)

            initialize_schema(connection)
            initialize_schema(connection)

            table_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'main'
                  AND table_name IN ('ingest_runs', 'sources', 'documents', 'chunks')
                """
            ).fetchone()[0]
            self.assertEqual(table_count, 4)

    def test_schema_contains_core_document_and_chunk_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "docemoria.duckdb"
            connection = open_database(db_path)
            self.addCleanup(connection.close)

            initialize_schema(connection)

            document_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info('documents')").fetchall()
            }
            chunk_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info('chunks')").fetchall()
            }

            self.assertTrue(
                {
                    "run_id",
                    "document_index",
                    "source_id",
                    "repo_relative_path",
                    "file_type",
                    "document_title",
                    "character_count",
                    "content",
                }.issubset(document_columns)
            )
            self.assertTrue(
                {
                    "run_id",
                    "document_index",
                    "chunk_index",
                    "start_char",
                    "end_char",
                    "character_count",
                    "document_title",
                    "heading_title",
                    "heading_level",
                    "heading_path",
                    "content",
                }.issubset(chunk_columns)
            )

    def test_initialize_schema_adds_document_title_column_to_existing_chunks_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "docemoria.duckdb"
            connection = open_database(db_path)
            self.addCleanup(connection.close)

            connection.execute(
                """
                CREATE TABLE chunks (
                    run_id BIGINT NOT NULL,
                    document_index INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    repo_relative_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    start_char INTEGER NOT NULL,
                    end_char INTEGER NOT NULL,
                    character_count INTEGER NOT NULL,
                    heading_title TEXT,
                    heading_level INTEGER,
                    heading_path TEXT,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_id, document_index, chunk_index)
                )
                """
            )

            initialize_schema(connection)

            chunk_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info('chunks')").fetchall()
            }
            self.assertIn("document_title", chunk_columns)

    def test_ingest_docset_persists_rows_in_core_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repos" / "sample-docs"
            config_path = root / "configs" / "docsets" / "sample.yaml"
            db_path = root / "data" / "docemoria.duckdb"
            (repo / "docs").mkdir(parents=True)
            config_path.parent.mkdir(parents=True)

            (repo / "docs" / "intro.md").write_text("# Intro\nabcdef\n", encoding="utf-8")
            (repo / "notes.txt").write_text("remember this\n", encoding="utf-8")
            config_path.write_text(
                "\n".join(
                    [
                        "source_id: sample",
                        "label: Sample docs",
                        "repo_path: ../../repos/sample-docs",
                        "chunking:",
                        "  strategy: fixed-windows",
                        "  max_chars: 5",
                        "  overlap_chars: 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = ingest_docset(config_path, db_path=db_path)

            self.assertEqual(result.source_id, "sample")
            self.assertEqual(result.document_count, 2)
            self.assertEqual(result.status, "success")
            self.assertTrue(result.db_path.endswith("data/docemoria.duckdb"))

            connection = open_database(db_path)
            self.addCleanup(connection.close)

            run_row = connection.execute(
                """
                SELECT status, document_count, chunk_count
                FROM ingest_runs
                WHERE run_id = ?
                """,
                [result.run_id],
            ).fetchone()
            self.assertEqual(run_row, ("success", 2, result.chunk_count))

            source_row = connection.execute(
                """
                SELECT source_id, label, repo_path
                FROM sources
                WHERE source_id = ?
                """,
                [result.source_id],
            ).fetchone()
            self.assertEqual(source_row[0], "sample")
            self.assertEqual(source_row[1], "Sample docs")
            self.assertEqual(source_row[2], str(repo.resolve()))

            document_title_row = connection.execute(
                "SELECT document_title FROM documents WHERE run_id = ? AND document_index = 0",
                [result.run_id],
            ).fetchone()
            self.assertEqual(document_title_row[0], "Intro")

            chunk_document_title_row = connection.execute(
                """
                SELECT document_title
                FROM chunks
                WHERE run_id = ? AND document_index = 0 AND chunk_index = 0
                """,
                [result.run_id],
            ).fetchone()
            self.assertEqual(chunk_document_title_row[0], "Intro")

            document_count = connection.execute("SELECT COUNT(*) FROM documents WHERE run_id = ?", [result.run_id]).fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks WHERE run_id = ?", [result.run_id]).fetchone()[0]
            self.assertEqual(document_count, result.document_count)
            self.assertEqual(chunk_count, result.chunk_count)

    def test_fetch_ingest_run_summary_returns_latest_run_with_persisted_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "docemoria.duckdb"
            connection = open_database(db_path)
            self.addCleanup(connection.close)
            initialize_schema(connection)

            connection.execute(
                """
                INSERT INTO ingest_runs (run_id, source_id, status, document_count, chunk_count, finished_at)
                VALUES (1, 'alpha', 'success', 10, 20, CURRENT_TIMESTAMP)
                """
            )
            connection.execute(
                """
                INSERT INTO ingest_runs (run_id, source_id, status, document_count, chunk_count, finished_at)
                VALUES (2, 'beta', 'success', 3, 4, CURRENT_TIMESTAMP)
                """
            )

            connection.execute(
                """
                INSERT INTO documents (
                    run_id,
                    document_index,
                    source_id,
                    repo_relative_path,
                    absolute_path,
                    file_type,
                    document_title,
                    character_count,
                    content
                )
                VALUES
                    (2, 0, 'beta', 'docs/a.md', '/tmp/a.md', 'markdown', 'Doc A', 11, 'hello world'),
                    (2, 1, 'beta', 'docs/b.md', '/tmp/b.md', 'markdown', 'Doc B', 5, 'abcde')
                """
            )
            connection.execute(
                """
                INSERT INTO chunks (
                    run_id,
                    document_index,
                    chunk_index,
                    source_id,
                    repo_relative_path,
                    file_type,
                    start_char,
                    end_char,
                    character_count,
                    heading_title,
                    heading_level,
                    heading_path,
                    content
                )
                VALUES
                    (2, 0, 0, 'beta', 'docs/a.md', 'markdown', 0, 5, 5, NULL, NULL, NULL, 'hello'),
                    (2, 1, 0, 'beta', 'docs/b.md', 'markdown', 0, 5, 5, NULL, NULL, '["Intro"]', 'abcde'),
                    (2, 1, 1, 'beta', 'docs/b.md', 'markdown', 0, 2, 2, NULL, NULL, '["Intro","Details"]', 'ab')
                """
            )

            summary = fetch_ingest_run_summary(connection)
            self.assertEqual(summary.run_id, 2)
            self.assertEqual(summary.source_id, "beta")
            self.assertEqual(summary.document_count, 3)
            self.assertEqual(summary.chunk_count, 4)
            self.assertEqual(summary.persisted_document_count, 2)
            self.assertEqual(summary.persisted_chunk_count, 3)
            self.assertEqual(summary.persisted_chunk_heading_path_count, 2)
            self.assertEqual(summary.status, "success")

    def test_fetch_ingest_run_summary_raises_for_missing_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "docemoria.duckdb"
            connection = open_database(db_path)
            self.addCleanup(connection.close)
            initialize_schema(connection)

            with self.assertRaisesRegex(StorageError, "Ingest run not found: 999"):
                fetch_ingest_run_summary(connection, run_id=999)

    def test_fetch_recent_ingest_runs_returns_recent_runs_with_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "docemoria.duckdb"
            connection = open_database(db_path)
            self.addCleanup(connection.close)
            initialize_schema(connection)

            connection.execute(
                """
                INSERT INTO ingest_runs (run_id, source_id, status, document_count, chunk_count, finished_at)
                VALUES
                    (1, 'alpha', 'success', 1, 1, CURRENT_TIMESTAMP),
                    (2, 'beta', 'failed', 3, 4, CURRENT_TIMESTAMP),
                    (3, 'gamma', 'success', 8, 10, CURRENT_TIMESTAMP)
                """
            )

            connection.execute(
                """
                INSERT INTO documents (
                    run_id,
                    document_index,
                    source_id,
                    repo_relative_path,
                    absolute_path,
                    file_type,
                    character_count,
                    content
                )
                VALUES
                    (3, 0, 'gamma', 'docs/c.md', '/tmp/c.md', 'markdown', 12, 'hello gamma'),
                    (3, 1, 'gamma', 'docs/d.md', '/tmp/d.md', 'markdown', 9, 'more gamma'),
                    (2, 0, 'beta', 'docs/b.md', '/tmp/b.md', 'markdown', 5, 'hello')
                """
            )
            connection.execute(
                """
                INSERT INTO chunks (
                    run_id,
                    document_index,
                    chunk_index,
                    source_id,
                    repo_relative_path,
                    file_type,
                    start_char,
                    end_char,
                    character_count,
                    heading_title,
                    heading_level,
                    heading_path,
                    content
                )
                VALUES
                    (3, 0, 0, 'gamma', 'docs/c.md', 'markdown', 0, 5, 5, NULL, NULL, '["Intro"]', 'hello'),
                    (3, 0, 1, 'gamma', 'docs/c.md', 'markdown', 5, 10, 5, NULL, NULL, NULL, ' gamma'),
                    (2, 0, 0, 'beta', 'docs/b.md', 'markdown', 0, 5, 5, NULL, NULL, NULL, 'hello')
                """
            )

            summaries = fetch_recent_ingest_runs(connection, limit=2)
            self.assertEqual([summary.run_id for summary in summaries], [3, 2])
            self.assertEqual(summaries[0].source_id, "gamma")
            self.assertEqual(summaries[0].persisted_document_count, 2)
            self.assertEqual(summaries[0].persisted_chunk_count, 2)
            self.assertEqual(summaries[0].persisted_chunk_heading_path_count, 1)
            self.assertEqual(summaries[1].source_id, "beta")


if __name__ == "__main__":
    unittest.main()

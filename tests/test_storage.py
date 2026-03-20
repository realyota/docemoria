import importlib.util
import tempfile
import unittest
from pathlib import Path

import docemoria

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
                    "heading_title",
                    "heading_level",
                    "content",
                }.issubset(chunk_columns)
            )


if __name__ == "__main__":
    unittest.main()

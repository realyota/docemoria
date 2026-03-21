import unittest

from docemoria.chunk_search import search_persisted_chunks
from docemoria.storage import StorageError


class ChunkSearchTests(unittest.TestCase):
    def test_search_persisted_chunks_maps_rows_and_parses_heading_path_json(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self.rows = rows
                self.calls: list[tuple[str, list[object]]] = []

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                self.calls.append((query, params))
                return FakeCursor(self.rows)

        connection = FakeConnection(
            [
                (
                    11,
                    "sample",
                    0,
                    2,
                    "docs/intro.md",
                    "Intro",
                    "Details",
                    '["Intro", "Details"]',
                    42,
                    "Needle content",
                )
            ]
        )

        matches = search_persisted_chunks(
            connection,  # type: ignore[arg-type]
            query="needle",
            source_id="sample",
            run_id=11,
            limit=3,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].run_id, 11)
        self.assertEqual(matches[0].heading_path, ["Intro", "Details"])
        self.assertEqual(connection.calls[0][1], ["needle", "sample", 11, 3])

    def test_search_persisted_chunks_parses_non_json_heading_path_as_single_value(self) -> None:
        class FakeCursor:
            def fetchall(self) -> list[tuple[object, ...]]:
                return [(7, "sample", 1, 0, "docs/faq.md", None, None, "FAQ", 12, "faq")]

        class FakeConnection:
            def execute(self, query: str, params: list[object]) -> FakeCursor:
                return FakeCursor()

        matches = search_persisted_chunks(FakeConnection(), query="faq")  # type: ignore[arg-type]

        self.assertEqual(matches[0].heading_path, ["FAQ"])

    def test_search_persisted_chunks_requires_non_empty_query(self) -> None:
        with self.assertRaisesRegex(StorageError, "Query must be a non-empty string"):
            search_persisted_chunks(object(), query="   ")  # type: ignore[arg-type]

    def test_search_persisted_chunks_requires_positive_limit(self) -> None:
        with self.assertRaisesRegex(StorageError, "Limit must be greater than 0"):
            search_persisted_chunks(object(), query="needle", limit=0)  # type: ignore[arg-type]

    def test_search_persisted_chunks_requires_non_empty_source_id_when_provided(self) -> None:
        with self.assertRaisesRegex(StorageError, "source_id filter must be a non-empty string"):
            search_persisted_chunks(object(), query="needle", source_id="   ")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

import unittest

from docemoria.chunk_search import (
    search_persisted_chunk_context,
    search_persisted_chunk_sections,
    search_persisted_chunks,
)
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
        call_params = connection.calls[0][1]
        self.assertEqual(call_params[0], "needle")
        self.assertEqual(call_params[4], "sample")
        self.assertEqual(call_params[5], 11)
        self.assertEqual(call_params[-1], 3)
        self.assertEqual(len(call_params), 7)
        self.assertEqual(call_params.count("needle"), 4)

    def test_search_persisted_chunks_matches_on_query_terms_and_metadata(self) -> None:
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
                    "docs/install.md",
                    "Installation Guide",
                    "Requirements",
                    '["Setup", "Requirements"]',
                    42,
                    "Install packages with pip",
                )
            ]
        )

        matches = search_persisted_chunks(
            connection,  # type: ignore[arg-type]
            query="Install guide",
            source_id="sample",
            limit=2,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(connection.calls[0][0].count("CAST(is_exact_match AS INTEGER)"), 1)
        self.assertIn("coalesce(lower(document_title), '')", connection.calls[0][0])
        self.assertIn("coalesce(lower(heading_title), '')", connection.calls[0][0])
        self.assertIn("coalesce(lower(heading_path), '')", connection.calls[0][0])
        call_params = connection.calls[0][1]
        self.assertEqual(call_params.count("install"), 4)
        self.assertEqual(call_params.count("guide"), 4)
        self.assertEqual(call_params.count("Install guide"), 4)

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

    def test_search_persisted_chunk_sections_groups_by_heading_path_with_fallbacks(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def __init__(
                self,
                *,
                search_rows: list[tuple[object, ...]],
                document_rows: list[tuple[object, ...]],
            ) -> None:
                self._search_rows = search_rows
                self._document_rows = document_rows
                self.calls: list[tuple[str, list[object]]] = []

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                self.calls.append((query, params))
                if "strpos(lower(content), lower(?)) > 0" in query:
                    return FakeCursor(self._search_rows)
                return FakeCursor(self._document_rows)

        connection = FakeConnection(
            search_rows=[
                (11, "sample", 0, 0, "docs/intro.md", "Intro", "Intro", '["Intro"]', 10, "match-a"),
                (11, "sample", 0, 1, "docs/intro.md", "Intro", "Intro", '["Intro"]', 11, "match-b"),
                (11, "sample", 0, 2, "docs/intro.md", "Intro", "Details", None, 12, "match-c"),
                (11, "sample", 0, 3, "docs/intro.md", "Intro", "Details", None, 13, "match-d"),
                (11, "sample", 0, 4, "docs/intro.md", "Intro", None, None, 14, "match-e"),
                (11, "sample", 0, 5, "docs/intro.md", "Intro", None, None, 15, "match-f"),
            ],
            document_rows=[
                (11, "sample", 0, 0, "docs/intro.md", "Intro", "Intro", '["Intro"]', 10, "match-a"),
                (11, "sample", 0, 1, "docs/intro.md", "Intro", "Intro", '["Intro"]', 11, "match-b"),
                (11, "sample", 0, 2, "docs/intro.md", "Intro", "Details", None, 12, "match-c"),
                (11, "sample", 0, 3, "docs/intro.md", "Intro", "Details", None, 13, "match-d"),
                (11, "sample", 0, 4, "docs/intro.md", "Intro", None, None, 14, "match-e"),
                (11, "sample", 0, 5, "docs/intro.md", "Intro", None, None, 15, "match-f"),
                (11, "sample", 0, 6, "docs/intro.md", "Intro", "Intro", '["Intro"]', 16, "context-intro"),
                (11, "sample", 0, 7, "docs/intro.md", "Intro", "Details", None, 17, "context-details"),
            ],
        )

        groups = search_persisted_chunk_sections(
            connection,  # type: ignore[arg-type]
            query="match",
            limit=6,
        )

        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0].heading_path, ["Intro"])
        self.assertEqual(groups[0].heading_title, "Intro")
        self.assertEqual(groups[0].match_chunk_indexes, [0, 1])
        self.assertEqual([chunk.chunk_index for chunk in groups[0].chunks], [0, 1, 6])
        self.assertEqual([chunk.is_match for chunk in groups[0].chunks], [True, True, False])

        self.assertIsNone(groups[1].heading_path)
        self.assertEqual(groups[1].heading_title, "Details")
        self.assertEqual(groups[1].match_chunk_indexes, [2, 3])
        self.assertEqual([chunk.chunk_index for chunk in groups[1].chunks], [2, 3, 7])
        self.assertEqual([chunk.is_match for chunk in groups[1].chunks], [True, True, False])

        self.assertIsNone(groups[2].heading_path)
        self.assertIsNone(groups[2].heading_title)
        self.assertEqual(groups[2].match_chunk_indexes, [4, 5])
        self.assertEqual([chunk.chunk_index for chunk in groups[2].chunks], [4, 5])
        self.assertEqual([chunk.is_match for chunk in groups[2].chunks], [True, True])

        self.assertEqual(len(connection.calls), 2)
        self.assertEqual(connection.calls[0][1][-1], 6)
        self.assertEqual(len(connection.calls[0][1]), 5)
        self.assertEqual(connection.calls[0][1].count("match"), 4)
        self.assertEqual(connection.calls[1][1], [11, "sample", 0])

    def test_search_persisted_chunk_sections_returns_empty_when_no_matches(self) -> None:
        class FakeCursor:
            def fetchall(self) -> list[tuple[object, ...]]:
                return []

        class FakeConnection:
            def __init__(self) -> None:
                self.call_count = 0

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                self.call_count += 1
                return FakeCursor()

        connection = FakeConnection()
        groups = search_persisted_chunk_sections(connection, query="missing")  # type: ignore[arg-type]
        self.assertEqual(groups, [])
        self.assertEqual(connection.call_count, 1)

    def test_search_persisted_chunk_sections_requires_positive_max_section_chars(self) -> None:
        with self.assertRaisesRegex(StorageError, "max_section_chars must be greater than 0 when provided"):
            search_persisted_chunk_sections(  # type: ignore[arg-type]
                object(),
                query="match",
                max_section_chars=0,
            )

    def test_search_persisted_chunk_sections_requires_integer_max_section_chars(self) -> None:
        with self.assertRaisesRegex(StorageError, "max_section_chars must be greater than 0 when provided"):
            search_persisted_chunk_sections(  # type: ignore[arg-type]
                object(),
                query="match",
                max_section_chars=True,
            )

        with self.assertRaisesRegex(StorageError, "max_section_chars must be greater than 0 when provided"):
            search_persisted_chunk_sections(  # type: ignore[arg-type]
                object(),
                query="match",
                max_section_chars=1.5,
            )

    def test_search_persisted_chunk_sections_limits_by_budget_and_prioritizes_matches_then_neighbors(
        self,
    ) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def __init__(
                self,
                *,
                search_rows: list[tuple[object, ...]],
                document_rows: list[tuple[object, ...]],
            ) -> None:
                self._search_rows = search_rows
                self._document_rows = document_rows

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                if "strpos(lower(content), lower(?)) > 0" in query:
                    return FakeCursor(self._search_rows)
                return FakeCursor(self._document_rows)

        search_rows = [
            (
                11,
                "sample",
                0,
                2,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "match-a",
            ),
            (
                11,
                "sample",
                0,
                4,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "match-b",
            ),
        ]
        document_rows = [
            (
                11,
                "sample",
                0,
                0,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "context-0",
            ),
            (
                11,
                "sample",
                0,
                1,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "context-1",
            ),
            (
                11,
                "sample",
                0,
                2,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "match-a",
            ),
            (
                11,
                "sample",
                0,
                3,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "context-3",
            ),
            (
                11,
                "sample",
                0,
                4,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "match-b",
            ),
            (
                11,
                "sample",
                0,
                5,
                "docs/intro.md",
                "Intro",
                "Details",
                '["Intro", "Details"]',
                10,
                "context-5",
            ),
        ]
        connection = FakeConnection(search_rows=search_rows, document_rows=document_rows)

        groups = search_persisted_chunk_sections(
            connection,  # type: ignore[arg-type]
            query="match",
            limit=2,
            max_section_chars=40,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].match_chunk_indexes, [2, 4])
        self.assertEqual([chunk.chunk_index for chunk in groups[0].chunks], [1, 2, 3, 4])
        self.assertEqual([chunk.is_match for chunk in groups[0].chunks], [False, True, False, True])
        self.assertEqual(sum(chunk.character_count for chunk in groups[0].chunks), 40)

    def test_search_persisted_chunk_sections_returns_empty_section_context_when_budget_too_small(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def execute(self, query: str, params: list[object]) -> FakeCursor:
                if "strpos(lower(content), lower(?)) > 0" in query:
                    return FakeCursor(
                        [
                            (
                                11,
                                "sample",
                                0,
                                1,
                                "docs/intro.md",
                                "Intro",
                                "Details",
                                '["Intro", "Details"]',
                                10,
                                "match-a",
                            )
                        ]
                    )
                return FakeCursor(
                    [
                        (
                            11,
                            "sample",
                            0,
                            0,
                            "docs/intro.md",
                            "Intro",
                            "Details",
                            '["Intro", "Details"]',
                            10,
                            "context-0",
                        ),
                        (
                            11,
                            "sample",
                            0,
                            1,
                            "docs/intro.md",
                            "Intro",
                            "Details",
                            '["Intro", "Details"]',
                            10,
                            "match-a",
                        ),
                        (
                            11,
                            "sample",
                            0,
                            2,
                            "docs/intro.md",
                            "Intro",
                            "Details",
                            '["Intro", "Details"]',
                            10,
                            "context-2",
                        ),
                    ]
                )

        groups = search_persisted_chunk_sections(
            FakeConnection(),  # type: ignore[arg-type]
            query="match",
            limit=1,
            max_section_chars=5,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].chunks, [])
        self.assertEqual(groups[0].match_chunk_indexes, [])

    def test_search_persisted_chunk_sections_skips_non_matches_when_no_match_fits_budget(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def execute(self, query: str, params: list[object]) -> FakeCursor:
                if "strpos(lower(content), lower(?)) > 0" in query:
                    return FakeCursor(
                        [
                            (
                                11,
                                "sample",
                                0,
                                1,
                                "docs/intro.md",
                                "Intro",
                                "Details",
                                '["Intro", "Details"]',
                                30,
                                "match-a",
                            )
                        ]
                    )
                return FakeCursor(
                    [
                        (
                            11,
                            "sample",
                            0,
                            0,
                            "docs/intro.md",
                            "Intro",
                            "Details",
                            '["Intro", "Details"]',
                            10,
                            "context-0",
                        ),
                        (
                            11,
                            "sample",
                            0,
                            1,
                            "docs/intro.md",
                            "Intro",
                            "Details",
                            '["Intro", "Details"]',
                            30,
                            "match-a",
                        ),
                        (
                            11,
                            "sample",
                            0,
                            2,
                            "docs/intro.md",
                            "Intro",
                            "Details",
                            '["Intro", "Details"]',
                            10,
                            "context-2",
                        ),
                    ]
                )

        groups = search_persisted_chunk_sections(
            FakeConnection(),  # type: ignore[arg-type]
            query="match",
            limit=1,
            max_section_chars=20,
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].chunks, [])
        self.assertEqual(groups[0].match_chunk_indexes, [])

    def test_search_persisted_chunk_sections_keeps_same_heading_path_separate_across_documents(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def __init__(
                self,
                *,
                search_rows: list[tuple[object, ...]],
                document_rows_by_key: dict[tuple[int, str, int], list[tuple[object, ...]]],
            ) -> None:
                self._search_rows = search_rows
                self._document_rows_by_key = document_rows_by_key
                self.calls: list[tuple[str, list[object]]] = []

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                self.calls.append((query, params))
                if "strpos(lower(content), lower(?)) > 0" in query:
                    return FakeCursor(self._search_rows)
                run_id, source_id, document_index = params
                return FakeCursor(self._document_rows_by_key[(int(run_id), str(source_id), int(document_index))])

        connection = FakeConnection(
            search_rows=[
                (11, "sample", 0, 0, "docs/intro.md", "Intro", "Details", '["Intro", "Details"]', 10, "match-a"),
                (11, "sample", 0, 1, "docs/intro.md", "Intro", "Details", '["Intro", "Details"]', 11, "match-b"),
                (11, "sample", 1, 0, "docs/faq.md", "FAQ", "Details", '["Intro", "Details"]', 12, "match-c"),
            ],
            document_rows_by_key={
                (11, "sample", 0): [
                    (11, "sample", 0, 0, "docs/intro.md", "Intro", "Details", '["Intro", "Details"]', 10, "match-a"),
                    (11, "sample", 0, 1, "docs/intro.md", "Intro", "Details", '["Intro", "Details"]', 11, "match-b"),
                    (
                        11,
                        "sample",
                        0,
                        2,
                        "docs/intro.md",
                        "Intro",
                        "Details",
                        '["Intro", "Details"]',
                        13,
                        "context-a",
                    ),
                ],
                (11, "sample", 1): [
                    (11, "sample", 1, 0, "docs/faq.md", "FAQ", "Details", '["Intro", "Details"]', 12, "match-c"),
                    (11, "sample", 1, 1, "docs/faq.md", "FAQ", "Details", '["Intro", "Details"]', 14, "context-b"),
                ],
            },
        )

        groups = search_persisted_chunk_sections(
            connection,  # type: ignore[arg-type]
            query="match",
            limit=3,
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].document_index, 0)
        self.assertEqual(groups[0].match_chunk_indexes, [0, 1])
        self.assertEqual([chunk.chunk_index for chunk in groups[0].chunks], [0, 1, 2])
        self.assertEqual([chunk.is_match for chunk in groups[0].chunks], [True, True, False])

        self.assertEqual(groups[1].document_index, 1)
        self.assertEqual(groups[1].match_chunk_indexes, [0])
        self.assertEqual([chunk.chunk_index for chunk in groups[1].chunks], [0, 1])
        self.assertEqual([chunk.is_match for chunk in groups[1].chunks], [True, False])

        self.assertEqual(len(connection.calls), 3)
        self.assertEqual(connection.calls[0][1][-1], 3)
        self.assertEqual(len(connection.calls[0][1]), 5)
        self.assertEqual(connection.calls[0][1].count("match"), 4)
        self.assertEqual(connection.calls[1][1], [11, "sample", 0])
        self.assertEqual(connection.calls[2][1], [11, "sample", 1])

    def test_search_persisted_chunk_context_groups_matches_and_expands_sibling_window(self) -> None:
        class FakeCursor:
            def __init__(self, rows: list[tuple[object, ...]]) -> None:
                self._rows = rows

            def fetchall(self) -> list[tuple[object, ...]]:
                return self._rows

        class FakeConnection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, list[object]]] = []

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                self.calls.append((query, params))
                if "strpos(lower(content), lower(?)) > 0" in query:
                    return FakeCursor(
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
                                30,
                                "match-a",
                            ),
                            (
                                11,
                                "sample",
                                0,
                                4,
                                "docs/intro.md",
                                "Intro",
                                "Details",
                                '["Intro", "Details"]',
                                31,
                                "match-b",
                            ),
                            (
                                11,
                                "sample",
                                1,
                                1,
                                "docs/faq.md",
                                "FAQ",
                                "General",
                                '["FAQ", "General"]',
                                32,
                                "match-c",
                            ),
                        ]
                    )

                run_id, source_id, document_index = params
                if (run_id, source_id, document_index) == (11, "sample", 0):
                    return FakeCursor(
                        [
                            (
                                11,
                                "sample",
                                0,
                                0,
                                "docs/intro.md",
                                "Intro",
                                "Overview",
                                '["Intro", "Overview"]',
                                10,
                                "chunk-0",
                            ),
                            (
                                11,
                                "sample",
                                0,
                                1,
                                "docs/intro.md",
                                "Intro",
                                "Overview",
                                '["Intro", "Overview"]',
                                11,
                                "chunk-1",
                            ),
                            (
                                11,
                                "sample",
                                0,
                                2,
                                "docs/intro.md",
                                "Intro",
                                "Details",
                                '["Intro", "Details"]',
                                12,
                                "chunk-2",
                            ),
                            (
                                11,
                                "sample",
                                0,
                                3,
                                "docs/intro.md",
                                "Intro",
                                "Details",
                                '["Intro", "Details"]',
                                13,
                                "chunk-3",
                            ),
                            (
                                11,
                                "sample",
                                0,
                                4,
                                "docs/intro.md",
                                "Intro",
                                "Details",
                                '["Intro", "Details"]',
                                14,
                                "chunk-4",
                            ),
                            (
                                11,
                                "sample",
                                0,
                                5,
                                "docs/intro.md",
                                "Intro",
                                "Summary",
                                '["Intro", "Summary"]',
                                15,
                                "chunk-5",
                            ),
                        ]
                    )
                if (run_id, source_id, document_index) == (11, "sample", 1):
                    return FakeCursor(
                        [
                            (
                                11,
                                "sample",
                                1,
                                0,
                                "docs/faq.md",
                                "FAQ",
                                "General",
                                '["FAQ", "General"]',
                                20,
                                "faq-0",
                            ),
                            (
                                11,
                                "sample",
                                1,
                                1,
                                "docs/faq.md",
                                "FAQ",
                                "General",
                                '["FAQ", "General"]',
                                21,
                                "faq-1",
                            ),
                            (
                                11,
                                "sample",
                                1,
                                2,
                                "docs/faq.md",
                                "FAQ",
                                "General",
                                '["FAQ", "General"]',
                                22,
                                "faq-2",
                            ),
                        ]
                    )
                raise AssertionError(f"Unexpected query params: {params}")

        connection = FakeConnection()

        groups = search_persisted_chunk_context(
            connection,  # type: ignore[arg-type]
            query="match",
            limit=3,
            sibling_chunks_before=1,
            sibling_chunks_after=1,
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].document_index, 0)
        self.assertEqual(groups[0].match_chunk_indexes, [2, 4])
        self.assertEqual([chunk.chunk_index for chunk in groups[0].chunks], [1, 2, 3, 4, 5])
        self.assertEqual([chunk.is_match for chunk in groups[0].chunks], [False, True, False, True, False])

        self.assertEqual(groups[1].document_index, 1)
        self.assertEqual(groups[1].match_chunk_indexes, [1])
        self.assertEqual([chunk.chunk_index for chunk in groups[1].chunks], [0, 1, 2])
        self.assertEqual([chunk.is_match for chunk in groups[1].chunks], [False, True, False])

        self.assertEqual(len(connection.calls), 3)
        self.assertEqual(connection.calls[0][1][-1], 3)
        self.assertEqual(len(connection.calls[0][1]), 5)
        self.assertEqual(connection.calls[0][1].count("match"), 4)
        self.assertEqual(connection.calls[1][1], [11, "sample", 0])
        self.assertEqual(connection.calls[2][1], [11, "sample", 1])

    def test_search_persisted_chunk_context_returns_empty_when_no_matches_found(self) -> None:
        class FakeCursor:
            def fetchall(self) -> list[tuple[object, ...]]:
                return []

        class FakeConnection:
            def __init__(self) -> None:
                self.call_count = 0

            def execute(self, query: str, params: list[object]) -> FakeCursor:
                self.call_count += 1
                return FakeCursor()

        connection = FakeConnection()
        groups = search_persisted_chunk_context(connection, query="missing")  # type: ignore[arg-type]
        self.assertEqual(groups, [])
        self.assertEqual(connection.call_count, 1)

    def test_search_persisted_chunk_context_requires_non_negative_sibling_before(self) -> None:
        with self.assertRaisesRegex(StorageError, "sibling_chunks_before must be greater than or equal to 0"):
            search_persisted_chunk_context(
                object(),
                query="needle",
                sibling_chunks_before=-1,
            )  # type: ignore[arg-type]

    def test_search_persisted_chunk_context_requires_non_negative_sibling_after(self) -> None:
        with self.assertRaisesRegex(StorageError, "sibling_chunks_after must be greater than or equal to 0"):
            search_persisted_chunk_context(
                object(),
                query="needle",
                sibling_chunks_after=-1,
            )  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

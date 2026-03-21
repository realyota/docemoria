from pathlib import Path
import unittest

from docemoria.chunking import ChunkingError, chunk_document, chunk_documents
from docemoria.document_loading import SourceDocument


class ChunkingTests(unittest.TestCase):
    def test_chunk_document_splits_content_into_overlapping_windows(self) -> None:
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.md"),
            repo_relative_path="docs/sample.md",
            content="abcdefghij",
            file_type="markdown",
        )

        chunks = chunk_document(document, max_chars=5, overlap_chars=2)

        self.assertEqual(
            [(chunk.chunk_index, chunk.start_char, chunk.end_char, chunk.content) for chunk in chunks],
            [
                (0, 0, 5, "abcde"),
                (1, 3, 8, "defgh"),
                (2, 6, 10, "ghij"),
            ],
        )
        self.assertEqual([(chunk.heading_title, chunk.heading_level) for chunk in chunks], [(None, None), (None, None), (None, None)])
        self.assertEqual([chunk.heading_path for chunk in chunks], [None, None, None])

    def test_chunk_documents_preserves_document_order_and_indexes(self) -> None:
        documents = [
            SourceDocument(
                source_id="sample",
                absolute_path=Path("/tmp/one.md"),
                repo_relative_path="docs/one.md",
                content="12345",
                file_type="markdown",
            ),
            SourceDocument(
                source_id="sample",
                absolute_path=Path("/tmp/two.txt"),
                repo_relative_path="docs/two.txt",
                content="abcdef",
                file_type="text",
            ),
        ]

        chunks = chunk_documents(documents, max_chars=4, overlap_chars=1)

        self.assertEqual(
            [(chunk.document_index, chunk.chunk_index, chunk.repo_relative_path, chunk.content) for chunk in chunks],
            [
                (0, 0, "docs/one.md", "1234"),
                (0, 1, "docs/one.md", "45"),
                (1, 0, "docs/two.txt", "abcd"),
                (1, 1, "docs/two.txt", "def"),
            ],
        )

    def test_chunk_document_uses_markdown_sections_for_heading_boundaries(self) -> None:
        content = "# Intro\nalpha\nbeta\n## Details\ngamma\n"
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.md"),
            repo_relative_path="docs/sample.md",
            content=content,
            file_type="markdown",
        )

        second_heading_start = content.index("## Details\n")

        chunks = chunk_document(
            document,
            strategy="markdown-sections",
            max_chars=100,
            overlap_chars=10,
        )

        self.assertEqual(
            [(chunk.chunk_index, chunk.start_char, chunk.end_char, chunk.content) for chunk in chunks],
            [
                (0, 0, second_heading_start, "# Intro\nalpha\nbeta\n"),
                (1, second_heading_start, len(content), "## Details\ngamma\n"),
            ],
        )
        self.assertEqual([(chunk.heading_title, chunk.heading_level) for chunk in chunks], [("Intro", 1), ("Details", 2)])
        self.assertEqual([chunk.heading_path for chunk in chunks], [("Intro",), ("Intro", "Details")])

    def test_chunk_document_windows_oversized_markdown_section_without_crossing_headings(self) -> None:
        content = "# Root\n## Intro\nabcdefghij\n## Next\nok\n"
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.md"),
            repo_relative_path="docs/sample.md",
            content=content,
            file_type="markdown",
        )

        intro_heading_start = content.index("## Intro\n")
        next_heading_start = content.index("## Next\n")

        chunks = chunk_document(
            document,
            strategy="markdown-sections",
            max_chars=12,
            overlap_chars=2,
        )

        self.assertEqual(
            [(chunk.chunk_index, chunk.start_char, chunk.end_char, chunk.content) for chunk in chunks],
            [
                (0, 0, intro_heading_start, "# Root\n"),
                (1, intro_heading_start, 19, "## Intro\nabc"),
                (2, 17, next_heading_start, "bcdefghij\n"),
                (3, next_heading_start, len(content), "## Next\nok\n"),
            ],
        )
        self.assertEqual(
            [(chunk.heading_title, chunk.heading_level) for chunk in chunks],
            [("Root", 1), ("Intro", 2), ("Intro", 2), ("Next", 2)],
        )
        self.assertEqual(
            [chunk.heading_path for chunk in chunks],
            [("Root",), ("Root", "Intro"), ("Root", "Intro"), ("Root", "Next")],
        )

    def test_chunk_document_markdown_sections_falls_back_to_fixed_windows_without_headings(self) -> None:
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.md"),
            repo_relative_path="docs/sample.md",
            content="abcdefghij",
            file_type="markdown",
        )

        chunks = chunk_document(
            document,
            strategy="markdown-sections",
            max_chars=5,
            overlap_chars=2,
        )

        self.assertEqual(
            [(chunk.chunk_index, chunk.start_char, chunk.end_char, chunk.content) for chunk in chunks],
            [
                (0, 0, 5, "abcde"),
                (1, 3, 8, "defgh"),
                (2, 6, 10, "ghij"),
            ],
        )
        self.assertEqual([(chunk.heading_title, chunk.heading_level) for chunk in chunks], [(None, None), (None, None), (None, None)])
        self.assertEqual([chunk.heading_path for chunk in chunks], [None, None, None])

    def test_chunk_document_markdown_sections_falls_back_to_fixed_windows_for_text_files(self) -> None:
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.txt"),
            repo_relative_path="docs/sample.txt",
            content="abcdefghij",
            file_type="text",
        )

        chunks = chunk_document(
            document,
            strategy="markdown-sections",
            max_chars=5,
            overlap_chars=2,
        )

        self.assertEqual(
            [(chunk.chunk_index, chunk.start_char, chunk.end_char, chunk.content) for chunk in chunks],
            [
                (0, 0, 5, "abcde"),
                (1, 3, 8, "defgh"),
                (2, 6, 10, "ghij"),
            ],
        )
        self.assertEqual([(chunk.heading_title, chunk.heading_level) for chunk in chunks], [(None, None), (None, None), (None, None)])
        self.assertEqual([chunk.heading_path for chunk in chunks], [None, None, None])

    def test_chunk_document_fixed_windows_sets_nearest_markdown_heading_metadata(self) -> None:
        content = "# Intro\nabc\n## Next\ndef\n"
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.md"),
            repo_relative_path="docs/sample.md",
            content=content,
            file_type="markdown",
        )

        chunks = chunk_document(
            document,
            strategy="fixed-windows",
            max_chars=6,
            overlap_chars=0,
        )

        self.assertEqual(
            [(chunk.start_char, chunk.end_char, chunk.heading_title, chunk.heading_level, chunk.heading_path) for chunk in chunks],
            [
                (0, 6, "Intro", 1, ("Intro",)),
                (6, 12, "Intro", 1, ("Intro",)),
                (12, 18, "Next", 2, ("Intro", "Next")),
                (18, 24, "Next", 2, ("Intro", "Next")),
            ],
        )

    def test_chunk_document_rejects_invalid_overlap(self) -> None:
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.md"),
            repo_relative_path="docs/sample.md",
            content="abc",
            file_type="markdown",
        )

        with self.assertRaises(ChunkingError) as context:
            chunk_document(document, max_chars=3, overlap_chars=3)

        self.assertIn("must be smaller than chunking.max_chars", str(context.exception))

    def test_chunk_document_rejects_unknown_strategy(self) -> None:
        document = SourceDocument(
            source_id="sample",
            absolute_path=Path("/tmp/sample.md"),
            repo_relative_path="docs/sample.md",
            content="abc",
            file_type="markdown",
        )

        with self.assertRaises(ChunkingError) as context:
            chunk_document(document, strategy="unknown", max_chars=3, overlap_chars=1)

        self.assertIn("Unsupported chunking.strategy", str(context.exception))


if __name__ == "__main__":
    unittest.main()

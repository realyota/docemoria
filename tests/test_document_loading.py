from pathlib import Path
import tempfile
import unittest

from docemoria.config import load_docset_config
from docemoria.document_loading import DocumentLoadingError, load_documents


class DocumentLoadingTests(unittest.TestCase):
    def test_load_documents_from_config_returns_structured_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "repos" / "sample-docs"
            config_path = root / "configs" / "docsets" / "sample.yaml"
            (repo / "docs").mkdir(parents=True)
            config_path.parent.mkdir(parents=True)

            (repo / "docs" / "intro.md").write_text("# Intro\n", encoding="utf-8")
            (repo / "notes.txt").write_text("Remember this.\n", encoding="utf-8")

            config_path.write_text(
                "source_id: sample\nlabel: Sample\nrepo_path: ../../repos/sample-docs\n",
                encoding="utf-8",
            )

            documents = load_documents(load_docset_config(config_path))

            self.assertEqual([document.repo_relative_path for document in documents], ["docs/intro.md", "notes.txt"])
            self.assertEqual(documents[0].source_id, "sample")
            self.assertEqual(documents[0].absolute_path, (repo / "docs" / "intro.md").resolve())
            self.assertEqual(documents[0].file_type, "markdown")
            self.assertEqual(documents[0].document_title, "Intro")
            self.assertEqual(documents[0].content, "# Intro\n")
            self.assertEqual(documents[1].file_type, "text")
            self.assertEqual(documents[1].document_title, "Remember this.")

    def test_load_documents_accepts_explicit_paths_with_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            doc_path = repo / "docs" / "intro.md"
            doc_path.parent.mkdir(parents=True)
            doc_path.write_text("# Hello\nBody\n", encoding="utf-8")

            documents = load_documents([doc_path], source_id="sample", repo_root=repo)

            self.assertEqual(len(documents), 1)
            self.assertEqual(documents[0].repo_relative_path, "docs/intro.md")
            self.assertEqual(documents[0].document_title, "Hello")

    def test_load_documents_rejects_unsupported_file_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            binary_path = repo / "docs" / "image.png"
            binary_path.parent.mkdir(parents=True)
            binary_path.write_bytes(b"\x89PNG\r\n")

            with self.assertRaises(DocumentLoadingError) as context:
                load_documents([binary_path], source_id="sample", repo_root=repo)

            self.assertIn("Unsupported source file type", str(context.exception))

    def test_load_documents_raises_for_non_utf8_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            bad_path = repo / "docs" / "broken.md"
            bad_path.parent.mkdir(parents=True)
            bad_path.write_bytes(b"\xff\xfe\x00\x00")

            with self.assertRaises(DocumentLoadingError) as context:
                load_documents([bad_path], source_id="sample", repo_root=repo)

            self.assertIn("not valid UTF-8 text", str(context.exception))

    def test_load_documents_uses_first_non_empty_text_line_as_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir)
            doc_path = repo / "notes.txt"
            doc_path.write_text("\n\nRemember this first\nThen this\n", encoding="utf-8")

            documents = load_documents([doc_path], source_id="sample", repo_root=repo)

            self.assertEqual(documents[0].document_title, "Remember this first")


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docemoria import cli


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


if __name__ == "__main__":
    unittest.main()

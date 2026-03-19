import contextlib
import io
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


if __name__ == "__main__":
    unittest.main()

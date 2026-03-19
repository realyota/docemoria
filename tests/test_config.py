from pathlib import Path
import tempfile
import unittest

from docemoria.config import ConfigError, load_docset_config, load_docset_configs


class DocsetConfigTests(unittest.TestCase):
    def test_load_example_config(self) -> None:
        config = load_docset_config(Path("configs/docsets/example.yaml"))
        self.assertEqual(config.source_id, "example-docs")
        self.assertEqual(config.chunking.strategy, "markdown-sections")
        self.assertEqual(config.providers.generation.model, "gpt-5.4")
        self.assertIn("Answer questions", config.prompts.qa_style)
        self.assertIn("Compress documentation", config.prompts.compression_style)

    def test_new_prompt_fields_default_to_empty_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir) / "minimal.yaml"
            tmp.write_text(
                "source_id: minimal\nlabel: Minimal\nrepo_path: docs/minimal\n",
                encoding="utf-8",
            )

            config = load_docset_config(tmp)
            self.assertEqual(config.prompts.qa_style, "")
            self.assertEqual(config.prompts.compression_style, "")

    def test_ingest_defaults_include_markdown_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir) / "minimal.yaml"
            tmp.write_text(
                "source_id: minimal\nlabel: Minimal\nrepo_path: docs/minimal\n",
                encoding="utf-8",
            )

            config = load_docset_config(tmp)
            self.assertEqual(config.ingest.include_globs, ["**/*.md", "**/*.txt"])
            self.assertEqual(config.ingest.exclude_globs, [])

    def test_ingest_globs_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir) / "scoped.yaml"
            tmp.write_text(
                "\n".join(
                    [
                        "source_id: scoped",
                        "label: Scoped",
                        "repo_path: docs/scoped",
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

            config = load_docset_config(tmp)
            self.assertEqual(config.ingest.include_globs, ["docs/**/*.md"])
            self.assertEqual(config.ingest.exclude_globs, ["docs/archive/**"])

    def test_invalid_ingest_globs_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir) / "broken.yaml"
            tmp.write_text(
                "\n".join(
                    [
                        "source_id: broken",
                        "label: Broken",
                        "repo_path: docs/broken",
                        "ingest:",
                        "  include_globs: docs/**/*.md",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_docset_config(tmp)

    def test_disabled_docset_is_skipped_from_directory_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / "enabled.yaml").write_text(
                "source_id: enabled\nlabel: Enabled\nrepo_path: docs/enabled\nenabled: true\n",
                encoding="utf-8",
            )
            (tmp / "disabled.yaml").write_text(
                "source_id: disabled\nlabel: Disabled\nrepo_path: docs/disabled\nenabled: false\n",
                encoding="utf-8",
            )

            configs = load_docset_configs(tmp)
            self.assertEqual([config.source_id for config in configs], ["enabled"])

    def test_missing_required_field_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir) / "broken.yaml"
            tmp.write_text("label: Broken\nrepo_path: docs/broken\n", encoding="utf-8")

            with self.assertRaises(ConfigError):
                load_docset_config(tmp)


if __name__ == "__main__":
    unittest.main()

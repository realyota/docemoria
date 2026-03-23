from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docemoria.config import ConfigError, load_docset_config, load_docset_configs
from docemoria.discovery import DiscoveryError, discover_docset_files, resolve_docset_repo_path


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

    def test_retrieval_max_section_chars_defaults_to_none(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={"source_id": "minimal", "label": "Minimal", "repo_path": "docs/minimal"},
        ):
            config = load_docset_config(Path("configs/docsets/minimal.yaml"))

        self.assertIsNone(config.retrieval.max_section_chars)

    def test_retrieval_context_chunk_windows_default_to_one(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={"source_id": "minimal", "label": "Minimal", "repo_path": "docs/minimal"},
        ):
            config = load_docset_config(Path("configs/docsets/minimal.yaml"))

        self.assertEqual(config.retrieval.context_before_chunks, 1)
        self.assertEqual(config.retrieval.context_after_chunks, 1)

    def test_retrieval_context_chunk_windows_can_be_set(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={
                "source_id": "scoped",
                "label": "Scoped",
                "repo_path": "docs/scoped",
                "retrieval": {"context_before_chunks": 0, "context_after_chunks": 3},
            },
        ):
            config = load_docset_config(Path("configs/docsets/with-context-window.yaml"))

        self.assertEqual(config.retrieval.context_before_chunks, 0)
        self.assertEqual(config.retrieval.context_after_chunks, 3)

    def test_retrieval_context_before_chunks_must_be_non_negative(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={
                "source_id": "scoped",
                "label": "Scoped",
                "repo_path": "docs/scoped",
                "retrieval": {"context_before_chunks": -1},
            },
        ):
            with self.assertRaises(ConfigError):
                load_docset_config(Path("configs/docsets/invalid-context-before.yaml"))

    def test_retrieval_context_after_chunks_rejects_boolean(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={
                "source_id": "scoped",
                "label": "Scoped",
                "repo_path": "docs/scoped",
                "retrieval": {"context_after_chunks": True},
            },
        ):
            with self.assertRaises(ConfigError):
                load_docset_config(Path("configs/docsets/invalid-context-after-bool.yaml"))

    def test_retrieval_max_section_chars_can_be_set(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={
                "source_id": "scoped",
                "label": "Scoped",
                "repo_path": "docs/scoped",
                "retrieval": {"max_section_chars": 900},
            },
        ):
            config = load_docset_config(Path("configs/docsets/with-limit.yaml"))

        self.assertEqual(config.retrieval.max_section_chars, 900)

    def test_retrieval_max_section_chars_must_be_positive(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={
                "source_id": "scoped",
                "label": "Scoped",
                "repo_path": "docs/scoped",
                "retrieval": {"max_section_chars": 0},
            },
        ):
            with self.assertRaises(ConfigError):
                load_docset_config(Path("configs/docsets/invalid-limit.yaml"))

    def test_retrieval_max_section_chars_rejects_boolean(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={
                "source_id": "scoped",
                "label": "Scoped",
                "repo_path": "docs/scoped",
                "retrieval": {"max_section_chars": True},
            },
        ):
            with self.assertRaises(ConfigError):
                load_docset_config(Path("configs/docsets/invalid-limit-bool.yaml"))

    def test_retrieval_max_section_chars_rejects_non_integral_float(self) -> None:
        with patch(
            "docemoria.config._read_yaml",
            return_value={
                "source_id": "scoped",
                "label": "Scoped",
                "repo_path": "docs/scoped",
                "retrieval": {"max_section_chars": 1.5},
            },
        ):
            with self.assertRaises(ConfigError):
                load_docset_config(Path("configs/docsets/invalid-limit-float.yaml"))

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

    def test_repo_path_is_resolved_from_config_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "configs" / "docsets" / "example.yaml"
            repo_root = root / "repos" / "example-docs"
            config_path.parent.mkdir(parents=True)
            repo_root.mkdir(parents=True)
            config_path.write_text(
                "source_id: example\nlabel: Example\nrepo_path: ../../repos/example-docs\n",
                encoding="utf-8",
            )

            config = load_docset_config(config_path)
            resolved = resolve_docset_repo_path(config)
            self.assertEqual(resolved, repo_root.resolve())

    def test_discover_docset_files_applies_include_and_exclude_globs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = root / "docsets" / "sample-docs"
            (repo / "docs").mkdir(parents=True)
            (repo / "docs" / "keep.md").write_text("keep", encoding="utf-8")
            (repo / "docs" / "skip.md").write_text("skip", encoding="utf-8")
            (repo / "notes.txt").write_text("ignore", encoding="utf-8")

            config_path = root / "configs" / "docsets" / "sample.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "\n".join(
                    [
                        "source_id: sample",
                        "label: Sample",
                        "repo_path: ../../docsets/sample-docs",
                        "ingest:",
                        "  include_globs:",
                        "    - docs/**/*.md",
                        "  exclude_globs:",
                        "    - docs/skip.md",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_docset_config(config_path)
            files = discover_docset_files(config)
            self.assertEqual(files, [(repo / "docs" / "keep.md").resolve()])

    def test_discover_docset_files_raises_for_missing_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "configs" / "docsets" / "missing.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "source_id: missing\nlabel: Missing\nrepo_path: docsets/missing\n",
                encoding="utf-8",
            )

            config = load_docset_config(config_path)
            with self.assertRaises(DiscoveryError):
                discover_docset_files(config)


if __name__ == "__main__":
    unittest.main()

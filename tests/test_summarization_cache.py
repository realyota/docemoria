import hashlib
import unittest
from unittest.mock import patch

from docemoria.config import DocsetConfig, PromptConfig, ProviderModelConfig, ProvidersConfig
from docemoria.summarize import summarize_run


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]] | None = None, one_row: tuple[object, ...] | None = None) -> None:
        self._rows = [] if rows is None else rows
        self._one_row = one_row

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def fetchone(self) -> tuple[object, ...] | None:
        return self._one_row


class FakeConnection:
    def __init__(
        self,
        documents_rows: list[tuple[object, ...]],
        run_state: tuple[object, ...] | None,
        document_summary_rows: list[tuple[object, ...]],
    ) -> None:
        self.documents_rows = documents_rows
        self.run_state = run_state
        self.document_summary_rows = document_summary_rows
        self.calls: list[tuple[str, list[object]]] = []

    def execute(self, query: str, params: list[object]) -> FakeCursor | None:
        normalized = query.strip().upper()
        self.calls.append((query, list(params)))
        if normalized.startswith("SELECT DOCUMENT_INDEX") and "FROM DOCUMENTS" in normalized:
            return FakeCursor(rows=self.documents_rows)
        if normalized.startswith("SELECT SUMMARY") and "FROM DOCUMENTS" in normalized:
            return FakeCursor(rows=self.document_summary_rows)
        if normalized.startswith("SELECT SUMMARY") and "FROM INGEST_RUNS" in normalized:
            return FakeCursor(one_row=self.run_state)
        return None


class FakeProvider:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or []
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return f"Summary for call {len(self.calls)}"


def _test_config() -> DocsetConfig:
    return DocsetConfig(
        source_id="sample",
        label="Sample",
        repo_path=".",
        prompts=PromptConfig(compression_style="Compact bullets"),
        providers=ProvidersConfig(generation=ProviderModelConfig(provider="openai", model="gpt-5.4")),
    )


def _run_summary_checksum(compression_style: str, document_summaries: list[str]) -> str:
    payload = f"{compression_style}\n\n{'\n\n'.join(document_summaries)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SummarizationRunCacheTests(unittest.TestCase):
    def test_summarize_run_skips_regeneration_when_run_summary_input_unchanged(self) -> None:
        config = _test_config()
        documents_rows = [
            (0, "Doc A", "cs-a", "summary a", "cs-a"),
            (1, "Doc B", "cs-b", "summary b", "cs-b"),
        ]
        existing_checksum = _run_summary_checksum(config.prompts.compression_style, ["summary a", "summary b"])
        connection = FakeConnection(
            documents_rows=documents_rows,
            run_state=("old summary", existing_checksum),
            document_summary_rows=[("summary a",), ("summary b",)],
        )
        fake_provider = FakeProvider()

        with patch("docemoria.summarize.OpenAIGenerationProvider", return_value=fake_provider):
            summarize_run(connection, config, run_id=11)

        update_calls = [call for call in connection.calls if call[0].strip().upper().startswith("UPDATE")]
        self.assertEqual(len(fake_provider.calls), 0)
        self.assertEqual(len(update_calls), 0)

    def test_summarize_run_regenerates_and_persists_checksum_when_input_changes(self) -> None:
        config = _test_config()
        documents_rows = [
            (0, "Doc A", "cs-a", "summary a", "cs-a"),
            (1, "Doc B", "cs-b", "summary b", "cs-b"),
        ]
        connection = FakeConnection(
            documents_rows=documents_rows,
            run_state=("old summary", "old-checksum"),
            document_summary_rows=[("summary a",), ("summary b",)],
        )
        fake_provider = FakeProvider(["run-level summary"])

        with patch("docemoria.summarize.OpenAIGenerationProvider", return_value=fake_provider):
            summarize_run(connection, config, run_id=11)

        update_calls = [call for call in connection.calls if call[0].strip().upper().startswith("UPDATE")]
        self.assertEqual(len(fake_provider.calls), 1)
        self.assertEqual(len(update_calls), 1)
        update_query, update_params = update_calls[0]
        self.assertIn("summary_input_checksum", update_query)
        expected_checksum = _run_summary_checksum(config.prompts.compression_style, ["summary a", "summary b"])
        self.assertEqual(update_params[0], "run-level summary")
        self.assertEqual(update_params[1], expected_checksum)
        self.assertEqual(update_params[2], 11)


if __name__ == "__main__":
    unittest.main()

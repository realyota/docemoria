import unittest
from unittest.mock import patch

from docemoria.config import DocsetConfig, PromptConfig, ProviderModelConfig, ProvidersConfig
from docemoria.summarize import summarize_run


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)


class FakeConnection:
    def __init__(self, select_rows: list[list[tuple[object, ...]]]) -> None:
        self._select_rows = [list(rows) for rows in select_rows]
        self.calls: list[tuple[str, list[object]]] = []

    def execute(self, query: str, params: list[object]) -> FakeCursor | None:
        self.calls.append((query, list(params)))
        if query.strip().upper().startswith("SELECT"):
            rows = self._select_rows.pop(0) if self._select_rows else []
            return FakeCursor(rows)
        return None


class FakeProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return f"Summary for call {len(self.calls)}"


def _test_config() -> DocsetConfig:
    return DocsetConfig(
        source_id="sample",
        label="Sample",
        repo_path=".",
        prompts=PromptConfig(compression_style="Compact bullets"),
        providers=ProvidersConfig(generation=ProviderModelConfig(provider="openai", model="gpt-5.4")),
    )


class SummarizationTests(unittest.TestCase):
    def test_summarize_run_updates_changed_documents_and_writes_global_summary(self) -> None:
        connection = FakeConnection(
            select_rows=[
                [
                    (0, "Alpha content", "cs-alpha", None, None),
                    (1, "Beta content", "cs-beta", "already there", "cs-beta"),
                    (2, "Gamma content", "cs-gamma", "stale", "different-checksum"),
                ],
                [
                    ("Summary for call 1",),
                    ("already there",),
                    ("Summary for call 2",),
                ],
            ]
        )
        fake_provider = FakeProvider("gpt-5.4")

        with patch("docemoria.summarize.OpenAIGenerationProvider", return_value=fake_provider) as provider_ctor:
            summarize_run(connection, _test_config(), run_id=11)

        self.assertEqual(len(provider_ctor.call_args_list), 1)
        self.assertEqual(connection.calls[0][1], [11])
        self.assertEqual(connection.calls[1][1], ["Summary for call 1", "cs-alpha", 11, 0])
        self.assertEqual(connection.calls[2][1], ["Summary for call 2", "cs-gamma", 11, 2])
        self.assertEqual(connection.calls[3][1], [11])
        self.assertEqual(connection.calls[4][1], ["Summary for call 3", 11])
        self.assertEqual(len(fake_provider.calls), 3)
        self.assertIn("Document Content:\nAlpha content", fake_provider.calls[0])
        self.assertIn("Document Content:\nGamma content", fake_provider.calls[1])
        self.assertIn("Document Summaries:\n\nSummary for call 1\n\nalready there\n\nSummary for call 2", fake_provider.calls[2])

    def test_summarize_run_clears_global_summary_when_no_document_summaries_exist(self) -> None:
        connection = FakeConnection(
            select_rows=[
                [],
                [],
            ]
        )
        fake_provider = FakeProvider("gpt-5.4")

        with patch("docemoria.summarize.OpenAIGenerationProvider", return_value=fake_provider):
            summarize_run(connection, _test_config(), run_id=11)

        self.assertEqual(len(fake_provider.calls), 0)
        update_calls = [call for call in connection.calls if call[0].strip().upper().startswith("UPDATE")]
        self.assertEqual(len(update_calls), 1)
        self.assertEqual(update_calls[0][1], [11])
        self.assertIn("SET summary = NULL", update_calls[0][0])

    def test_summarize_run_skips_when_generation_provider_not_configured(self) -> None:
        config = _test_config()
        config.providers.generation = None

        with self.assertRaisesRegex(ValueError, "Docset config must include a generation provider"):
            summarize_run(FakeConnection([[]]), config, run_id=11)


if __name__ == "__main__":
    unittest.main()

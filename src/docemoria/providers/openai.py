from typing import Any

from openai import OpenAI

from docemoria.providers.generation import GenerationError, GenerationProvider


class OpenAIGenerationProvider(GenerationProvider):
    def __init__(self, model: str, api_key: str | None = None, **kwargs: Any):
        self.model = model
        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            content = response.choices[0].message.content
            if not content:
                raise GenerationError("OpenAI API returned an empty response")
            return content
        except GenerationError:
            raise
        except Exception as exc:
            raise GenerationError(f"OpenAI generation failed: {exc}") from exc

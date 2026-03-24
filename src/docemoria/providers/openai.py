from typing import Any
from openai import OpenAI

from docemoria.providers.generation import GenerationProvider

class OpenAIGenerationProvider(GenerationProvider):
    def __init__(self, model: str, api_key: str | None = None, **kwargs: Any):
        self.model = model
        self.client = OpenAI(api_key=api_key) # API key can be None, then it picks from env vars

    def generate(self, prompt: str, **kwargs: Any) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                **kwargs
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            # TODO: Implement better error handling and logging
            print(f"Error calling OpenAI API: {e}")
            return ""


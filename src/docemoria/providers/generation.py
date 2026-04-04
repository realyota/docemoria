from abc import ABC, abstractmethod


class GenerationError(RuntimeError):
    """Raised when generation provider cannot produce valid output."""


class GenerationProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Abstract method to generate text based on a given prompt.
        Implementations should handle specific provider APIs and model calls.
        """
        pass

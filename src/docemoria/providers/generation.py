from abc import ABC, abstractmethod

class GenerationProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Abstract method to generate text based on a given prompt.
        Implementations should handle specific provider APIs and model calls.
        """
        pass

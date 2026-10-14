from abc import ABC, abstractmethod


class LLMError(Exception):
    """Base exception for LLM operations."""
    pass


class LLMConfigurationError(LLMError):
    """Raised when LLM provider or required credentials are not configured."""
    pass


class LLMGenerationError(LLMError):
    """Raised when the LLM provider fails during inference."""
    pass


class BaseLLMProvider(ABC):
    """Minimal interface for LLM question answering."""

    @abstractmethod
    def generate_answer(self, prompt: str) -> str:
        """
        Generate a text response given a prompt.
        Must raise LLMConfigurationError if misconfigured,
        or LLMGenerationError if API call fails.
        """
        pass

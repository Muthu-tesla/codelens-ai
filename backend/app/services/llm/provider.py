import logging
from typing import Any
import httpx

from app.core.config import settings
from app.services.llm.base import (
    BaseLLMProvider,
    LLMConfigurationError,
    LLMGenerationError,
)

logger = logging.getLogger(__name__)


class OpenAILLMProvider(BaseLLMProvider):
    """
    Standard HTTP-based OpenAI-compatible LLM provider.
    Uses httpx for isolated, zero-framework HTTP inference.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate_answer(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMConfigurationError(
                "LLM provider is not configured. Please set the LLM_API_KEY environment variable."
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.0,
        }

        def _sanitize(msg: str) -> str:
            if self.api_key and len(self.api_key) > 5 and self.api_key in msg:
                return msg.replace(self.api_key, "[REDACTED_API_KEY]")
            return msg

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                if response.status_code != 200:
                    sanitized_text = _sanitize(response.text)
                    logger.error("LLM provider returned status %d: %s", response.status_code, sanitized_text)
                    raise LLMGenerationError(
                        f"LLM provider error (status {response.status_code}): {sanitized_text}"
                    )
                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise LLMGenerationError("LLM returned empty choices in response.")
                content = choices[0].get("message", {}).get("content", "")
                return content.strip()
        except httpx.RequestError as exc:
            sanitized_err = _sanitize(str(exc))
            logger.error("HTTP error connecting to LLM provider: %s", sanitized_err)
            raise LLMGenerationError(f"Failed to connect to LLM provider: {sanitized_err}") from exc
        except Exception as exc:
            if isinstance(exc, (LLMConfigurationError, LLMGenerationError)):
                raise
            sanitized_err = _sanitize(str(exc))
            logger.error("Unexpected error during LLM generation: %s", sanitized_err)
            raise LLMGenerationError(f"LLM generation failed: {sanitized_err}") from exc


class LLMService:
    """
    Singleton service managing the active LLM provider.
    Allows injecting mock providers for testing without making live API calls.
    """

    def __init__(self) -> None:
        self._provider: BaseLLMProvider | None = None

    def get_provider(self) -> BaseLLMProvider:
        if self._provider is None:
            self._provider = OpenAILLMProvider()
        return self._provider

    def set_provider(self, provider: BaseLLMProvider | None) -> None:
        """Inject a custom or mock provider."""
        self._provider = provider

    def generate_answer(self, prompt: str) -> str:
        """Generate answer via current provider."""
        provider = self.get_provider()
        return provider.generate_answer(prompt)


llm_service = LLMService()

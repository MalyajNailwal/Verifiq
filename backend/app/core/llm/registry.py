"""Provider registry: builds the configured LLMClient from Settings."""

import logging

from app.core.config import Settings
from app.core.llm.base import LLMClient
from app.core.llm.claude_client import ClaudeClient
from app.core.llm.gemini_client import GeminiClient
from app.core.llm.mock_client import MockLLMClient
from app.core.llm.openai_client import OpenAIClient
from app.core.llm.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[LLMClient]] = {
    "claude": ClaudeClient,
    "openai": OpenAIClient,
    "gemini": GeminiClient,
    "openrouter": OpenRouterClient,
    "mock": MockLLMClient,
}


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Instantiate the provider named by settings.llm_provider (constraint #6)."""
    settings = settings or Settings()  # type: ignore[call-arg]
    cls = _PROVIDERS.get(settings.llm_provider)
    if cls is None:  # guarded by Settings validation, but belt-and-braces
        raise ValueError(f"Unknown LLM provider '{settings.llm_provider}'")
    kwargs = {
        "model": settings.llm_model,
        "max_retries": settings.llm_max_retries,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    if cls is OpenRouterClient:
        kwargs["base_url"] = settings.openrouter_base_url
    client = cls(**kwargs)
    logger.info("llm_client_ready provider=%s model=%s", client.provider, client.model)
    return client

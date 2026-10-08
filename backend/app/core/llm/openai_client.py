"""OpenAI adapter (optional extra: pip install '.[openai]'). SDK imported lazily."""

import logging
import os

from app.core.llm.base import LLMClient, LLMUnavailableError
from app.schemas.llm import LLMResponse

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient):
    """OpenAI ChatCompletions adapter."""

    provider = "openai"

    def _complete_raw(self, prompt: str, system: str | None = None) -> LLMResponse:
        try:
            from openai import OpenAI  # lazy import
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailableError("openai package not installed") from exc

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMUnavailableError("OPENAI_API_KEY not set")

        client = OpenAI(api_key=api_key)
        try:
            resp = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system or "Return only valid JSON. Never guess."},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as exc:
            raise LLMUnavailableError(f"openai API error: {exc}") from exc

        choice = resp.choices[0] if resp.choices else None
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=choice.message.content or "" if choice else "",
            model=resp.model,
            provider=self.provider,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            finish_reason=getattr(choice, "finish_reason", None),
        )

"""Google Gemini adapter (optional extra: pip install '.[gemini]'). SDK imported lazily."""

import logging
import os

from app.core.llm.base import LLMClient, LLMUnavailableError
from app.schemas.llm import LLMResponse

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    """Gemini via google-genai."""

    provider = "gemini"

    def _complete_raw(self, prompt: str, system: str | None = None) -> LLMResponse:
        try:
            from google import genai  # lazy import
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailableError("google-genai package not installed") from exc

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMUnavailableError("GEMINI_API_KEY not set")

        client = genai.Client(api_key=api_key)
        try:
            resp = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    system_instruction=system or "Return only valid JSON. Never guess.",
                ),
            )
        except Exception as exc:
            raise LLMUnavailableError(f"gemini API error: {exc}") from exc

        usage = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text=resp.text or "",
            model=self.model,
            provider=self.provider,
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            completion_tokens=getattr(usage, "candidates_token_count", None),
            total_tokens=getattr(usage, "total_token_count", None),
            finish_reason=str(resp.candidates[0].finish_reason) if resp.candidates else None,
        )

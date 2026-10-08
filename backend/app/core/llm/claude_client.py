"""Anthropic (Claude) adapter. Installed by default; SDK imported lazily."""

import logging
import os

from app.core.llm.base import LLMClient, LLMUnavailableError
from app.schemas.llm import LLMResponse

logger = logging.getLogger(__name__)


class ClaudeClient(LLMClient):
    """Claude via the Anthropic Messages API."""

    provider = "claude"

    def _complete_raw(self, prompt: str, system: str | None = None) -> LLMResponse:
        try:
            import anthropic  # lazy import: app boots without the SDK/keys
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailableError("anthropic package not installed") from exc

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMUnavailableError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=api_key)
        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system
                or "You are a meticulous document-verification assistant. "
                "Return only valid JSON. Never guess; use null for missing values.",
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise LLMUnavailableError(f"anthropic API error: {exc}") from exc

        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        usage = getattr(msg, "usage", None)
        return LLMResponse(
            text=text,
            model=msg.model,
            provider=self.provider,
            prompt_tokens=getattr(usage, "input_tokens", None),
            completion_tokens=getattr(usage, "output_tokens", None),
            total_tokens=(getattr(usage, "input_tokens", 0) or 0)
            + (getattr(usage, "output_tokens", 0) or 0),
            finish_reason=getattr(msg, "stop_reason", None),
        )

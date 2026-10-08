"""OpenRouter adapter — one API key, any model (Claude, GPT, Gemini, Llama, ...).

OpenRouter exposes an OpenAI-compatible REST API, so we call it directly with
httpx (already a core dependency) — no provider SDK required.
Default model: anthropic/claude-sonnet-4 (set LLM_MODEL to switch, e.g.
"openai/gpt-4o-mini", "google/gemini-2.0-flash-001").
"""

import logging
import os

import httpx

from app.core.llm.base import LLMClient, LLMUnavailableError
from app.schemas.llm import LLMResponse

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 120.0


class OpenRouterClient(LLMClient):
    """Any-model client routed through openrouter.ai."""

    provider = "openrouter"

    def __init__(
        self, model: str, *, base_url: str = "https://openrouter.ai/api/v1", **kwargs
    ) -> None:
        super().__init__(model, **kwargs)
        self.base_url = base_url.rstrip("/")

    def _complete_raw(self, prompt: str, system: str | None = None) -> LLMResponse:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise LLMUnavailableError("OPENROUTER_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Optional attribution headers recommended by OpenRouter.
            "HTTP-Referer": "https://github.com/MalyajNailwal/Verifiq",
            "X-Title": "RWA DiligenceAI",
        }
        messages: list[dict[str, str]] = []
        messages.append(
            {
                "role": "system",
                "content": system
                or "Return only valid JSON. Never guess; use null for missing values.",
            }
        )
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        try:
            with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"openrouter network error: {exc}") from exc

        if resp.status_code == 401:
            raise LLMUnavailableError("openrouter auth failed (check OPENROUTER_API_KEY)")
        if resp.status_code == 429:
            raise LLMUnavailableError("openrouter rate limit / quota exceeded")
        if resp.status_code >= 400:
            raise LLMUnavailableError(f"openrouter error {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        choices = data.get("choices") or []
        text = choices[0]["message"]["content"] if choices else ""
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=data.get("model", self.model),
            provider=self.provider,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            finish_reason=(choices[0].get("finish_reason") if choices else None),
        )

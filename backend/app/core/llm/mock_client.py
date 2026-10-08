"""Deterministic mock client — used in tests and as a no-key fallback."""

import json
import logging

from app.core.llm.base import LLMClient
from app.schemas.llm import LLMResponse

logger = logging.getLogger(__name__)


class MockLLMClient(LLMClient):
    """Returns canned JSON keyed by a marker in the prompt, else echoes the prompt.

    Tests register canned responses:  client = MockLLMClient("mock")
    client.canned["extraction"] = '{"fields": []}'
    Then any prompt containing "extraction" gets that payload.
    """

    provider = "mock"

    def __init__(self, model: str = "mock-model", **kwargs) -> None:
        super().__init__(model, **kwargs)
        self.canned: dict[str, str] = {}
        self.calls: list[str] = []

    def _complete_raw(self, prompt: str, system: str | None = None) -> LLMResponse:
        self.calls.append(prompt)
        for marker, payload in self.canned.items():
            if marker in prompt:
                return LLMResponse(
                    text=payload if isinstance(payload, str) else json.dumps(payload),
                    model=self.model,
                    provider=self.provider,
                    prompt_tokens=len(prompt) // 4,
                    completion_tokens=64,
                    finish_reason="stop",
                )
        # Default: valid, empty structured output shape.
        return LLMResponse(
            text=json.dumps({"fields": [], "document_summary": None, "is_readable": False}),
            model=self.model,
            provider=self.provider,
            prompt_tokens=len(prompt) // 4,
            completion_tokens=16,
            finish_reason="stop",
        )

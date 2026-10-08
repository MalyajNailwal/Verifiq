"""LLMClient interface — single swappable entry point for all LLM providers.

Contract (hard constraints):
- `complete_structured` validates every LLM output against a Pydantic schema
  and retries on invalid output (constraint #4).
- Providers are selected via LLM_PROVIDER env var (constraint #6).
- Every call is logged (provider, model, prompt name/version, tokens, latency).
"""

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.llm import LLMResponse

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Base error for LLM failures."""


class LLMUnavailableError(LLMError):
    """Provider unreachable / auth failure / quota exceeded."""


class LLMInvalidOutputError(LLMError):
    """Output could not be parsed or failed schema validation after all retries."""

    def __init__(self, message: str, last_raw: str | None = None) -> None:
        super().__init__(message)
        self.last_raw = last_raw


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> str:
    """Extract a JSON object from an LLM response (bare, fenced, or embedded)."""
    fenced = _JSON_BLOCK_RE.search(text)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in LLM output")
    return text[start : end + 1]


class LLMClient(ABC):
    """Abstract provider-agnostic LLM client."""

    provider: str = "abstract"

    def __init__(
        self, model: str, *, max_retries: int = 2, temperature: float = 0.0, max_tokens: int = 4096
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def _complete_raw(self, prompt: str, system: str | None = None) -> LLMResponse:
        """Provider-specific single completion call. Subclasses implement only this."""

    def complete(self, prompt: str, system: str | None = None) -> LLMResponse:
        """One completion call with timing + error normalization."""
        start = time.monotonic()
        try:
            resp = self._complete_raw(prompt, system)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMUnavailableError(f"{self.provider} call failed: {exc}") from exc
        resp.latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "llm_call provider=%s model=%s latency_ms=%s prompt_tokens=%s completion_tokens=%s",
            self.provider,
            resp.model,
            resp.latency_ms,
            resp.prompt_tokens,
            resp.completion_tokens,
        )
        return resp

    def complete_structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> T:
        """Completion -> JSON -> Pydantic validation, retrying on invalid output.

        Retries feed the validation error back so the model can self-correct.
        Raises LLMInvalidOutputError after exhausting retries (constraint #4).
        """
        last_raw: str | None = None
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            resp = self.complete(prompt, system)
            last_raw = resp.text
            try:
                raw_json = extract_json(resp.text)
                return schema.model_validate_json(raw_json)
            except (ValueError, ValidationError) as exc:
                last_error = exc
                logger.warning(
                    "llm_structured_validation_failed attempt=%d/%d schema=%s err=%s",
                    attempt + 1,
                    self.max_retries + 1,
                    schema.__name__,
                    exc,
                )
                prompt = (
                    f"{prompt}\n\nYour previous reply was not valid against the schema:\n"
                    f"{last_error}\nReturn ONLY corrected JSON matching the schema. "
                    f"Never invent values; use null."
                )
        raise LLMInvalidOutputError(
            f"Invalid LLM output for {schema.__name__} after "
            f"{self.max_retries + 1} attempts: {last_error}",
            last_raw=last_raw,
        )

    def healthcheck(self) -> bool:
        """Cheap connectivity probe; default is a 1-token completion."""
        try:
            self.complete("Reply with the single word: ok")
            return True
        except LLMError:
            return False

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} provider={self.provider} model={self.model}>"


def dumps(data: BaseModel | dict) -> str:
    """Compact JSON dump helper (shared by prompt builders)."""
    if isinstance(data, BaseModel):
        return data.model_dump_json(exclude_none=True)
    return json.dumps(data, ensure_ascii=False)

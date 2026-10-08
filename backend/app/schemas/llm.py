"""Schemas for LLM structured outputs and call results (constraint #4: everything validated)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ExtractionCandidate(BaseModel):
    """One extracted field as returned by the LLM. null value => not found, never guessed."""

    field_name: str = Field(max_length=64)
    value: Any | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_page: int | None = Field(default=None, ge=1)
    source_snippet: str | None = Field(default=None, max_length=500)
    reason: Literal["ok", "not_found", "ambiguous", "low_quality_scan"] | None = None

    @field_validator("value")
    @classmethod
    def _reject_empty_string(cls, v: Any) -> Any:
        """Empty string is ambiguous; force explicit null + reason instead."""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class ExtractionResult(BaseModel):
    """Top-level LLM extraction output for one document."""

    fields: list[ExtractionCandidate] = Field(default_factory=list)
    document_summary: str | None = None
    is_readable: bool = True


class SummaryResult(BaseModel):
    """LLM-written plain-English explanation for the report (rating itself is rule-based)."""

    summary: str = Field(min_length=1)


class LLMResponse(BaseModel):
    """Raw completion wrapper with usage metadata for logging."""

    text: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    finish_reason: str | None = None

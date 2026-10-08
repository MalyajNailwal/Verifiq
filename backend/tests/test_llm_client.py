"""LLMClient contract tests (constraint #4: schema-validated output with retry)."""

import pytest
from pydantic import BaseModel, Field, ValidationError

from app.core.llm import (
    LLMInvalidOutputError,
    MockLLMClient,
    extract_json,
    get_llm_client,
)
from app.schemas.llm import ExtractionResult


class Tiny(BaseModel):
    answer: int = Field(ge=0)


def test_extract_json_variants() -> None:
    assert extract_json('{"a": 1}') == '{"a": 1}'
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('Here you go:\n{"a": 1}\nThanks!') == '{"a": 1}'
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_complete_structured_validates_and_returns_model() -> None:
    client = MockLLMClient()
    client.canned["check"] = '{"answer": 3}'
    out = client.complete_structured("please check: check", Tiny)
    assert out.answer == 3


def test_complete_structured_retries_then_succeeds() -> None:
    client = MockLLMClient(max_retries=2)
    responses = iter(['{"answer": -1}', "not json at all", '{"answer": 5}'])

    def fake_raw(prompt: str, system=None):  # type: ignore[no-untyped-def]
        from app.schemas.llm import LLMResponse

        return LLMResponse(text=next(responses), model="mock-model", provider="mock", latency_ms=1)

    client._complete_raw = fake_raw  # type: ignore[method-assign]
    out = client.complete_structured("x", Tiny)
    assert out.answer == 5
    assert len(client.calls) == 0  # fake bypassed call recording; retries happened via complete


def test_complete_structured_raises_after_retries() -> None:
    client = MockLLMClient(max_retries=1)
    client.canned["x"] = "definitely not json"
    with pytest.raises(LLMInvalidOutputError):
        client.complete_structured("x", Tiny)


def test_extraction_schema_rejects_confidence_out_of_range() -> None:
    payload = '{"fields": [{"field_name": "owner_name", "value": null, "confidence": 1.5}]}'
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate_json(payload)


def test_extraction_schema_empty_string_becomes_null() -> None:
    out = ExtractionResult.model_validate_json(
        '{"fields": [{"field_name": "owner_name", "value": "  ", '
        '"confidence": 0.9, "reason": "ok"}]}'
    )
    assert out.fields[0].value is None


def test_registry_returns_mock(test_settings) -> None:
    client = get_llm_client(test_settings)
    assert client.provider == "mock"
    assert client.healthcheck() is True

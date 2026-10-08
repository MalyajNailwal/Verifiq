"""OpenRouter adapter tests — fully offline (httpx transport mocked)."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx
import pytest

from app.core.config import Settings
from app.core.llm import LLMUnavailableError, get_llm_client
from app.core.llm.openrouter_client import OpenRouterClient


def _client() -> OpenRouterClient:
    return OpenRouterClient("anthropic/claude-sonnet-4")


@contextmanager
def mock_transport(handler: Callable[[httpx.Request], httpx.Response]) -> Iterator[None]:
    """Patch httpx.Client to route all requests through a mock handler."""
    orig_init = httpx.Client.__init__

    def patched(self, *args, **kwargs):
        kwargs.pop("transport", None)
        kwargs.pop("timeout", None)
        orig_init(self, transport=httpx.MockTransport(handler), timeout=5.0, **kwargs)

    httpx.Client.__init__ = patched  # type: ignore[method-assign]
    try:
        yield
    finally:
        httpx.Client.__init__ = orig_init  # type: ignore[method-assign]


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "anthropic/claude-sonnet-4",
            "choices": [{"message": {"content": '{"answer": 1}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def test_openrouter_success(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    with mock_transport(lambda request: _ok_response()):
        resp = _client().complete("hi")
    assert resp.text == '{"answer": 1}'
    assert resp.provider == "openrouter"
    assert resp.total_tokens == 15
    assert resp.latency_ms is not None


def test_openrouter_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMUnavailableError, match="OPENROUTER_API_KEY"):
        _client().complete("hi")


def test_openrouter_auth_and_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")

    def _401(request):
        return httpx.Response(401, json={"error": "bad key"})

    def _429(request):
        return httpx.Response(429, json={"error": "quota"})

    with mock_transport(_401):
        with pytest.raises(LLMUnavailableError, match="auth failed"):
            _client().complete("hi")
    with mock_transport(_429):
        with pytest.raises(LLMUnavailableError, match="rate limit"):
            _client().complete("hi")


def test_registry_builds_openrouter(test_settings) -> None:
    settings = Settings(
        DATABASE_URL="sqlite://",
        LLM_PROVIDER="openrouter",
        LLM_MODEL="openai/gpt-4o-mini",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
    )  # type: ignore[call-arg]
    client = get_llm_client(settings)
    assert isinstance(client, OpenRouterClient)
    assert client.provider == "openrouter"
    assert client.base_url == "https://openrouter.ai/api/v1"

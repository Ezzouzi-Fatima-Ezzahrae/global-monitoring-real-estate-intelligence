"""Tests for src/services/llm_client.py.

No mock mode: these tests stub the HTTP transport (httpx.Client.post) that
sits underneath the real provider calls, the same technique used in
tests/test_tools.py, so the actual request-building/response-parsing/retry
code is what's under test — it just never leaves the machine.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

import time as time_module
from src.config import settings
from src.errors import MissingConfigurationError
from src.services.llm_client import GEMINI_API_BASE, LLMClient


def test_summarize_event_requires_llm_api_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    client = LLMClient()
    with pytest.raises(MissingConfigurationError, match="LLM_API_KEY"):
        client.summarize_event(
            agent_name="Test Agent",
            article_title="t",
            article_text="x",
            source_url="https://example.test/article",
        )


def test_complete_json_calls_gemini_with_correct_request_shape(monkeypatch):
    captured = {}

    def fake_post(self, url, params=None, headers=None, json=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers #15/10/2026 fix 
        captured["json"] = json
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"summary": "ok"}'}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    result = client.complete_json(provider="gemini", model="gemini-3.6-flash", api_key="k", prompt="hello")

    assert result == {"summary": "ok"}
    # 2026-10-15 fix: the Gemini key now travels in the x-goog-api-key header,
    # never in the URL query string (see _call_gemini_raw).
    assert captured["headers"] == {"x-goog-api-key": "k"}
    assert not captured["params"]
    assert captured["url"] == f"{GEMINI_API_BASE}/gemini-3.6-flash:generateContent"


def test_complete_json_calls_groq_with_bearer_auth(monkeypatch):
    captured = {}

    def fake_post(self, url, params=None, headers=None, json=None):
        captured["headers"] = headers
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    result = client.complete_json(provider="groq", model="m", api_key="secret", prompt="hi")

    assert result == {"ok": True}
    assert captured["headers"] == {"Authorization": "Bearer secret"}


def test_gemini_no_candidates_raises_with_prompt_feedback(monkeypatch):
    def fake_post(self, url, params=None, headers=None, json=None):
        return httpx.Response(
            200, json={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    with pytest.raises(ValueError, match="SAFETY"):
        client.complete_json(provider="gemini", model="m", api_key="k", prompt="p")


def test_post_with_retry_retries_transient_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(self, url, params=None, headers=None, json=None):
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, text="unavailable", request=httpx.Request("POST", url))
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(time_module, "sleep", lambda *_: None)
    client = LLMClient()
    result = client.complete_json(provider="gemini", model="m", api_key="k", prompt="p")

    assert result == {}
    assert calls["n"] == 2


def test_post_with_retry_does_not_retry_4xx(monkeypatch):
    calls = {"n": 0}

    def fake_post(self, url, params=None, headers=None, json=None):
        calls["n"] += 1
        return httpx.Response(401, text="bad key", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    with pytest.raises(httpx.HTTPStatusError):
        client.complete_json(provider="gemini", model="m", api_key="bad", prompt="p")

    assert calls["n"] == 1  # a 4xx will always fail the same way — retrying just delays finding out


def test_post_with_retry_retries_429_then_succeeds(monkeypatch):
    """2026-09-15 regression: a real production run showed every Judge
    assessment failing on a real Gemini 429 (free-tier rate limit) because
    429 used to be treated like any other 4xx and never retried. Confirm it
    now gets retried like a transient error, not raised immediately."""
    calls = {"n": 0}

    def fake_post(self, url, params=None, headers=None, json=None):
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, text="rate limited", request=httpx.Request("POST", url))
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(time_module, "sleep", lambda *_: None)
    client = LLMClient()
    result = client.complete_json(provider="gemini", model="m", api_key="k", prompt="p")

    assert result == {}
    assert calls["n"] == 2


def test_post_with_retry_honors_a_real_retry_after_header(monkeypatch):
    seen_delays = []

    def fake_post(self, url, params=None, headers=None, json=None):
        return httpx.Response(429, text="rate limited", headers={"Retry-After": "7"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(time_module, "sleep", lambda seconds: seen_delays.append(seconds))
    client = LLMClient()
    with pytest.raises(httpx.HTTPStatusError):
        client.complete_json(provider="gemini", model="m", api_key="k", prompt="p")

    assert seen_delays and seen_delays[0] == 7.0


def test_post_with_retry_eventually_gives_up_on_sustained_429(monkeypatch):
    calls = {"n": 0}

    def fake_post(self, url, params=None, headers=None, json=None):
        calls["n"] += 1
        return httpx.Response(429, text="rate limited", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(time_module, "sleep", lambda *_: None)
    client = LLMClient()
    with pytest.raises(httpx.HTTPStatusError):
        client.complete_json(provider="gemini", model="m", api_key="k", prompt="p")

    assert calls["n"] == 4  # real quota that never recovers must still fail, not retry forever


def test_post_with_retry_defaults_to_request_timeout_seconds(monkeypatch):
    # 2026-09-22 regression test: the document-upload timeout fix added an
    # optional timeout_seconds param to complete_json/_post_with_retry --
    # every existing caller (summarize_event, debate, Judge, chat,
    # translation) doesn't pass it, so this confirms they still get the
    # original, fast default rather than silently losing their timeout.
    monkeypatch.setattr(settings, "request_timeout_seconds", 7)
    captured = {}

    def fake_post(self, url, params=None, headers=None, json=None):
        captured["timeout"] = self.timeout
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    client.complete_json(provider="gemini", model="m", api_key="k", prompt="p")

    assert captured["timeout"].connect == 7


def test_extract_events_from_document_uses_document_analysis_timeout(monkeypatch):
    # The whole point of the fix: a document-analysis call gets the longer,
    # document-specific timeout instead of the fast per-article one, even
    # though it goes through the exact same complete_json/_post_with_retry
    # path as every other call.
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(settings, "request_timeout_seconds", 7)
    monkeypatch.setattr(settings, "document_analysis_timeout_seconds", 45)
    captured = {}

    def fake_post(self, url, params=None, headers=None, json=None):
        captured["timeout"] = self.timeout
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"events": []}'}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    events = client.extract_events_from_document(
        agent_name="Uploaded Document Agent",
        document_title="t",
        document_text="some real document text",
        source_url="https://example.test/documents/abc/pdf",
    )

    assert events == []
    assert captured["timeout"].connect == 45


def test_complete_json_gemini_default_max_output_tokens_unchanged(monkeypatch):
    # 2026-09-24 regression test: the fix below added an optional max_tokens
    # param to complete_json/_call_gemini_raw -- every existing caller
    # (summarize_event, debate, Judge, chat, translation) doesn't pass it,
    # so this confirms they still get the original 1500 cap rather than
    # silently losing it.
    captured = {}

    def fake_post(self, url, params=None, headers=None, json=None):
        captured["generationConfig"] = json["generationConfig"]
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    client.complete_json(provider="gemini", model="m", api_key="k", prompt="p")

    assert captured["generationConfig"]["maxOutputTokens"] == 1500


def test_extract_events_from_document_requests_more_completion_room(monkeypatch):
    # 2026-09-24 fix: a real upload was failing with nothing ever saved,
    # traced to Gemini's hardcoded 1500-token cap truncating a real
    # multi-event document response mid-JSON so it failed to parse. Confirm
    # document analysis now asks for settings.document_analysis_max_output_
    # tokens instead of the small per-article default.
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(settings, "document_analysis_max_output_tokens", 4000)
    captured = {}

    def fake_post(self, url, params=None, headers=None, json=None):
        captured["generationConfig"] = json["generationConfig"]
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"events": []}'}]}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    events = client.extract_events_from_document(
        agent_name="Uploaded Document Agent",
        document_title="t",
        document_text="some real document text",
        source_url="https://example.test/documents/abc/pdf",
    )

    assert events == []
    assert captured["generationConfig"]["maxOutputTokens"] == 4000


def test_extract_events_from_document_groq_fallback_also_gets_more_tokens(monkeypatch):
    # The 429-fallback path (a rate-limited primary provider) must not
    # silently drop back to Groq's own small default either.
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(settings, "groq_api_key", "gk")
    monkeypatch.setattr(settings, "document_analysis_max_output_tokens", 4000)
    monkeypatch.setattr(time_module, "sleep", lambda *_: None)
    captured = {}

    def fake_post(self, url, params=None, headers=None, json=None):
        if "generativelanguage" in url:
            # The primary (Gemini) provider is exhaustively rate-limited, so
            # extract_events_from_document falls back to Groq below.
            return httpx.Response(429, text="rate limited", request=httpx.Request("POST", url))
        captured["groq_max_tokens"] = json["max_tokens"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"events": []}'}}]}, request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = LLMClient()
    client.extract_events_from_document(
        agent_name="Uploaded Document Agent", document_title="t",
        document_text="some real document text", source_url="https://example.test/documents/abc/pdf",
    )

    assert captured["groq_max_tokens"] == 4000


def test_parse_json_response_handles_plain_json():
    parsed = LLMClient._parse_json_response('{"summary": "ok", "confidence": 0.5}')
    assert parsed == {"summary": "ok", "confidence": 0.5}


def test_parse_json_response_strips_markdown_fence():
    fenced = '```json\n{"summary": "ok", "confidence": 0.5}\n```'
    parsed = LLMClient._parse_json_response(fenced)
    assert parsed == {"summary": "ok", "confidence": 0.5}

# 2026-10-14 addition: complete_json_with_groq_fallback() mirrors the Groq-on-
# 429 fallback summarize_event already has, for stages that call
# complete_json() directly (the Judge). The cases below pin what must NOT
# fall back as strongly as what must.
def _status_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "http://x")
    return httpx.HTTPStatusError(str(status), request=req, response=httpx.Response(status, request=req))


def _client_with(monkeypatch, fail_with=None):
    client = LLMClient()
    calls = []

    def fake_complete_json(*, provider, model, api_key, prompt, **kwargs):
        calls.append((provider, kwargs))
        if provider != "groq" and fail_with is not None:
            raise _status_error(fail_with)
        return {"ok": True}

    monkeypatch.setattr(client, "complete_json", fake_complete_json)
    return client, calls


def test_fallback_switches_to_groq_on_a_persistent_429(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test")
    client, calls = _client_with(monkeypatch, fail_with=429)
    result = client.complete_json_with_groq_fallback(provider="gemini", model="m", api_key="k", prompt="p")
    assert result == {"ok": True}
    assert [c[0] for c in calls] == ["gemini", "groq"]


def test_fallback_does_not_mask_a_non_429_error(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test")
    client, calls = _client_with(monkeypatch, fail_with=401)
    with pytest.raises(httpx.HTTPStatusError):
        client.complete_json_with_groq_fallback(provider="gemini", model="m", api_key="k", prompt="p")
    assert [c[0] for c in calls] == ["gemini"]


def test_fallback_is_skipped_without_a_groq_key(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    client, calls = _client_with(monkeypatch, fail_with=429)
    with pytest.raises(httpx.HTTPStatusError):
        client.complete_json_with_groq_fallback(provider="gemini", model="m", api_key="k", prompt="p")
    assert [c[0] for c in calls] == ["gemini"]


def test_fallback_is_skipped_when_the_primary_provider_is_already_groq(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test")
    client = LLMClient()
    calls = []

    def always_429(*, provider, model, api_key, prompt, **kwargs):
        calls.append(provider)
        raise _status_error(429)

    monkeypatch.setattr(client, "complete_json", always_429)
    with pytest.raises(httpx.HTTPStatusError):
        client.complete_json_with_groq_fallback(provider="groq", model="m", api_key="k", prompt="p")
    assert calls == ["groq"]


def test_fallback_only_forwards_optional_arguments_that_were_set(monkeypatch):
    client, calls = _client_with(monkeypatch)
    client.complete_json_with_groq_fallback(provider="gemini", model="m", api_key="k", prompt="p")
    client.complete_json_with_groq_fallback(
        provider="gemini", model="m", api_key="k", prompt="p", timeout_seconds=45, max_tokens=4000
    )
    assert calls[0][1] == {}
    assert calls[1][1] == {"timeout_seconds": 45, "max_tokens": 4000}

# 2026-10-14 addition: pins the key-leak fix. httpx builds the error text from
# the real request, so this goes through a MockTransport instead of faking the
# response: a 401 is not retried, so the test is instant.
def test_a_gemini_http_error_never_contains_the_api_key(monkeypatch):
    real_client = httpx.Client
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["header"] = request.headers.get("x-goog-api-key")
        return httpx.Response(401, request=request, json={"error": "bad key"})

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        LLMClient().complete_json(provider="gemini", model="m", api_key="SECRET123", prompt="p")
    assert "SECRET123" not in str(excinfo.value)
    assert "SECRET123" not in seen["url"]
    assert seen["header"] == "SECRET123"
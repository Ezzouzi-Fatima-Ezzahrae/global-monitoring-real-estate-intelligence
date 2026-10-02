"""Tests for src/tools/web_search.py and src/tools/page_fetch.py.

There is no mock mode to test here — these tests stub the HTTP transport
(httpx) that sits underneath the real code, the same technique any test
suite uses to avoid hitting a real, paid API on every run. The parsing,
error handling, and MissingConfigurationError logic being exercised is the
actual production code path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from src.config import settings
from src.errors import MissingConfigurationError
from src.tools import compare_values, extract_content, fetch_page, web_search


def test_web_search_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "web_search_api_key", "")
    with pytest.raises(MissingConfigurationError, match="WEB_SEARCH_API_KEY"):
        web_search("anything")


def test_web_search_builds_request_and_parses_a_real_response_shape(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Real headline",
                        "url": "https://example.test/a",
                        "content": "snippet text",
                        "published_date": "2026-09-01",
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    results = web_search("morocco real estate", source_category="real_estate_sector", max_results=3)

    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["json"]["api_key"] == "test-fake-search-key"
    assert captured["json"]["query"] == "morocco real estate"
    assert "include_domains" not in captured["json"]  # not passed -> not sent at all
    assert len(results) == 1
    assert results[0].title == "Real headline"
    assert results[0].url == "https://example.test/a"


def test_web_search_passes_include_domains_through_to_tavily(monkeypatch):
    """Verified against the real Tavily API (see monitoring_agent.py's
    MONITORING_AGENTS comment): restricting to real, named outlets is what
    turns a generic query into a specific, real, fetchable article instead
    of a site's homepage. This test locks in that the parameter actually
    reaches the request."""
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return httpx.Response(200, json={"results": []}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    web_search("morocco central bank", include_domains=["en.hespress.com", "moroccoworldnews.com"])

    assert captured["json"]["include_domains"] == ["en.hespress.com", "moroccoworldnews.com"]


def test_web_search_drops_results_outside_include_domains(monkeypatch):
    """2026-09-16: two real calls against the live Tavily API returned
    results outside the requested include_domains (a Wikipedia article, a
    europeanceo.com article) when few of the requested domains had current
    matches for the query -- reproducible, not a one-off. Since
    MONITORING_AGENTS' include_domains lists are a curated, trusted-outlet
    restriction (see its module comment), web_search() now enforces that
    restriction itself on the results it gets back, rather than trusting
    the provider to always honor it."""
    def fake_post(url, json=None, timeout=None):
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "On-list article", "url": "https://en.hespress.com/some-article", "content": "..."},
                    {"title": "Off-list, unrequested", "url": "https://en.wikipedia.org/wiki/Morocco", "content": "..."},
                    {"title": "Subdomain of a requested domain", "url": "https://www.moroccoworldnews.com/x", "content": "..."},
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    results = web_search(
        "morocco real estate",
        max_results=5,
        include_domains=["en.hespress.com", "moroccoworldnews.com"],
    )

    urls = {r.url for r in results}
    assert urls == {"https://en.hespress.com/some-article", "https://www.moroccoworldnews.com/x"}


def test_web_search_recency_days_sets_news_topic_and_days(monkeypatch):
    """Verified against the real Tavily API: for fast-moving categories
    (political/economic news), this is what keeps results to the last N
    days instead of years-old matches. Off by default — see
    monitoring_agent.py's MONITORING_AGENTS comment for why it's not on for
    every category."""
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return httpx.Response(200, json={"results": []}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    web_search("central bank rate decision", recency_days=7)

    assert captured["json"]["topic"] == "news"
    assert captured["json"]["days"] == 7


def test_web_search_no_recency_days_omits_topic_and_days(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return httpx.Response(200, json={"results": []}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    web_search("marrakech real estate")

    assert "topic" not in captured["json"]
    assert "days" not in captured["json"]


def test_web_search_transient_failure_returns_empty_not_raise(monkeypatch):
    def raising_post(*args, **kwargs):
        raise httpx.ConnectError("simulated network blip")

    monkeypatch.setattr(httpx, "post", raising_post)
    # An honest empty result on a genuine transient failure (FR-14) — not a
    # fixture standing in for real data.
    assert web_search("x") == []


def test_fetch_page_rejects_non_html_content_type(monkeypatch):
    def fake_get(url, timeout=None, follow_redirects=True):
        return httpx.Response(
            200, headers={"content-type": "application/json"}, text="{}", request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fetch_page("https://example.test/data.json") is None


def test_fetch_page_returns_page_on_success(monkeypatch):
    def fake_get(url, timeout=None, follow_redirects=True):
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body>hi</body></html>",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    page = fetch_page("https://example.test/page")
    assert page is not None
    assert "<html" in page.html


def test_fetch_page_returns_none_on_genuine_failure(monkeypatch):
    def raising_get(*args, **kwargs):
        raise httpx.ConnectError("simulated network blip")

    monkeypatch.setattr(httpx, "get", raising_get)
    assert fetch_page("https://example.test/unreachable") is None


def test_extract_content_strips_html():
    page_html = "<html><body><h1>Title</h1><p>Body text 2026-01-02.</p></body></html>"
    content = extract_content(page_html)
    assert content.title == "Title"
    assert "Body text" in content.main_text
    assert content.detected_publish_date == "2026-01-02"


def test_compare_values_is_deterministic():
    result = compare_values([10.0, 20.0, 30.0])
    assert result.observed_avg == 20.0
    assert result.observed_min == 10.0
    assert result.observed_max == 30.0


def test_compare_values_empty_input_does_not_crash():
    result = compare_values([])
    assert result.observed_count == 0

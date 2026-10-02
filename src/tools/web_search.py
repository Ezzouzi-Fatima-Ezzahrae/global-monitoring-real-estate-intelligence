"""web_search tool.

Mirrors the tool design from the fact-checking project: a deterministic,
testable function agents call. There is no mock mode — WEB_SEARCH_API_KEY
is required, and its absence raises MissingConfigurationError immediately
rather than silently returning fixture data.

Once configured, calls a real search API (Tavily-style REST endpoint
assumed here; swap the URL/payload if a different provider is chosen — see
the "What we need from you" section of the README).

A genuine transient failure on a real call (network blip, timeout, a 5xx
from the provider) still returns an empty list and logs, rather than
raising into the caller — that's the fail-gracefully tool design principle
used throughout this project (FR-14: one source outage never crashes the
daily run), and it's not the same thing as fabrication: an empty result is
honest, a fixture standing in for a real one is not.

2026-09-16 addition: while adding new source domains for the monitoring
agents, two real calls against the live API returned articles OUTSIDE the
requested include_domains (a Wikipedia article with a 5-domain
Real Estate Sector list, europeanceo.com with a 4-domain Regional
MENA/Morocco list) -- reproducible, not a one-off fluke, and it went away
when the same query was re-run restricted to only the domains that were
actually returning matches. So Tavily's include_domains appears to be a
soft preference, not a hard filter, when few of the requested domains have
current indexed content for a query. Since MONITORING_AGENTS' whole point
is a curated, trusted outlet list (see its module comment), this module
now enforces that restriction itself after the real API call, rather than
trusting the provider to honor it -- see _matches_included_domain below.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    published_date: Optional[str] = None


def _matches_included_domain(url: str, include_domains: list[str]) -> bool:
    """True if url's host is one of include_domains, or a subdomain of one
    (so "en.hespress.com" still matches an include_domains entry of
    "hespress.com", and "www." is ignored either way)."""
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    for domain in include_domains:
        domain = domain.lower()
        if host == domain or host.endswith("." + domain):
            return True
    return False


def web_search(
    query: str,
    source_category: str = "global_political",
    max_results: int = 5,
    include_domains: Optional[list[str]] = None,
    recency_days: Optional[int] = None,
) -> list[SearchResult]:
    """Query for evidence. `source_category` is passed through for logging/
    future provider-side filtering; it no longer selects a fixture bucket,
    since there are no fixtures in the running system.

    `include_domains` restricts results to a specific list of real,
    named outlets (e.g. ["reuters.com", "apnews.com"]) — Tavily supports
    this natively. Verified against the real API: an unrestricted generic
    query often returns a site's homepage or a category-listing page rather
    than one article, which the downstream LLM then honestly summarizes as
    "this is a navigation menu" (not fabrication, but not a useful event
    either); the same query restricted to specific real outlets reliably
    returns a specific, real, fetchable article instead. See
    src/agents/monitoring_agent.py's MONITORING_AGENTS for the curated
    per-category domain lists this is called with.

    `recency_days`, when set, switches Tavily into `topic="news"` mode
    restricted to the last N days — verified directly against the real API
    to fix results that were otherwise years old, a poor fit for a *daily*
    intelligence digest. Also verified: this only helps for fast-moving,
    wire-service-style categories (global political/economic news) — for
    slower-moving categories (institutional real-estate research, regional
    Morocco coverage), Tavily's default relevance-ranked search across all
    indexed content (not just its news index) found better, more specific,
    still-recent real articles than "news mode" did. See
    src/agents/monitoring_agent.py's MONITORING_AGENTS for which agents use
    which, and why — this is a per-category judgment call, not a global
    default, so it defaults to None (off) here."""
    api_key = settings.require("web_search_api_key", "WEB_SEARCH_API_KEY")

    request_body: dict = {"api_key": api_key, "query": query, "max_results": max_results}
    if include_domains:
        request_body["include_domains"] = include_domains
    if recency_days:
        request_body["topic"] = "news"
        request_body["days"] = recency_days

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json=request_body,
            timeout=settings.request_timeout_seconds,
        )
        resp.raise_for_status()
        response_body = resp.json()
        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
                published_date=r.get("published_date"),
            )
            for r in response_body.get("results", [])[:max_results]
        ]
        if include_domains:
            before = len(results)
            results = [r for r in results if _matches_included_domain(r.url, include_domains)]
            if len(results) != before:
                logger.warning(
                    "web_search category=%s query=%r: Tavily returned %d result(s) outside "
                    "include_domains=%s; dropped them rather than citing an unvetted outlet",
                    source_category, query, before - len(results), include_domains,
                )
        logger.info("web_search category=%s query=%r -> %d results", source_category, query, len(results))
        return results
    except Exception as exc:
        logger.error("web_search failed category=%s query=%r: %s", source_category, query, exc)
        return []

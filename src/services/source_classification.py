"""Deterministic source classification (2026-09-24 addition, at Orchid
Island's request: every event must say what kind of source it came from
and how much weight that source's own claim deserves).

Deliberately NOT an LLM call: every monitoring agent already searches a
curated, real, named list of outlets (see src/agents/monitoring_agent.py's
MONITORING_AGENTS), so which real outlet an event came from is already
known for certain the moment its source_url is known -- classifying it is
a lookup, not a judgment call, and a lookup can't hallucinate the way an
extra model call could. YouTube (no fixed outlet list -- the whole
platform) is the one case genuinely without that certainty, so it gets the
honest, weaker default below rather than being upgraded on a guess.
"""
from __future__ import annotations

from urllib.parse import urlparse

from src.models.event import SourceQuality, SourceType

# International/official institutions whose own publications are a
# primary source for their own data and statements (not third-party
# reporting about them).
_GOVERNMENT_DOMAINS = {"imf.org", "worldbank.org", "eia.gov"}
_GOVERNMENT_TLD_SUFFIXES = (".gov",)

# A company's own LinkedIn page/announcement -- self-reported, but that is
# exactly what "official company announcement" means, so it's PRIMARY, the
# same as a company's own press release would be.
_LINKEDIN_DOMAINS = {"linkedin.com", "www.linkedin.com"}

# Real-estate/market research and advisory firms -- their own published
# research is closer to a "Report" than day-to-day news reporting.
_REPORT_DOMAINS = {
    "knightfrank.com", "knightfrank.co.uk", "jll.com", "cbre.com",
    "globalpropertyguide.com", "spglobal.com", "tradingeconomics.com",
}

# Established business/economic media and policy-research outlets --
# credible, named, real, but still third-party reporting/commentary, not
# the company or government itself.
_BUSINESS_MEDIA_DOMAINS = {
    "project-syndicate.org", "voxeu.org", "brookings.edu", "cfr.org", "mckinsey.com",
    "bloomberg.com", "cnbc.com", "ft.com", "economist.com", "hotelnewsnow.com", "skift.com",
}

_QUALITY_BY_TYPE = {
    SourceType.GOVERNMENT: SourceQuality.PRIMARY,
    SourceType.OFFICIAL_COMPANY: SourceQuality.PRIMARY,
    SourceType.LINKEDIN: SourceQuality.PRIMARY,
    SourceType.REPORT: SourceQuality.CREDIBLE_SECONDARY,
    SourceType.BUSINESS_MEDIA: SourceQuality.CREDIBLE_SECONDARY,
    SourceType.NEWS: SourceQuality.CREDIBLE_SECONDARY,
    SourceType.PDF: SourceQuality.CREDIBLE_SECONDARY,  # overridden per-event by document_agent.py when traceability is weak
    SourceType.OTHER: SourceQuality.EARLY_UNCONFIRMED,
}


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def classify_web_source(url: str) -> tuple[SourceType, SourceQuality]:
    """Classifies a real web-search-agent result by its real domain. Every
    domain here is already one of the curated, named, live-verified outlets
    in MONITORING_AGENTS's source_domains lists (see that file's own
    docstring) -- an unrecognized domain still gets a real, honest
    fallback (NEWS/CREDIBLE_SECONDARY) rather than crashing, since it
    passed that agent's own real include_domains filter to get here at
    all."""
    domain = _domain(url)
    if not domain:
        return SourceType.OTHER, SourceQuality.NOT_VERIFIED

    if domain in _LINKEDIN_DOMAINS:
        return SourceType.LINKEDIN, _QUALITY_BY_TYPE[SourceType.LINKEDIN]
    if domain in _GOVERNMENT_DOMAINS or domain.endswith(_GOVERNMENT_TLD_SUFFIXES):
        return SourceType.GOVERNMENT, _QUALITY_BY_TYPE[SourceType.GOVERNMENT]
    if domain in _REPORT_DOMAINS:
        return SourceType.REPORT, _QUALITY_BY_TYPE[SourceType.REPORT]
    if domain in _BUSINESS_MEDIA_DOMAINS:
        return SourceType.BUSINESS_MEDIA, _QUALITY_BY_TYPE[SourceType.BUSINESS_MEDIA]
    return SourceType.NEWS, _QUALITY_BY_TYPE[SourceType.NEWS]


def classify_youtube_source() -> tuple[SourceType, SourceQuality]:
    """YouTube search has no curated outlet allowlist (see
    MonitoringAgentConfig.source_domains's own docstring) -- any channel on
    the platform can match, so this is honestly the weakest tier rather
    than upgraded on a guess about which channel it happened to be."""
    return SourceType.OTHER, SourceQuality.EARLY_UNCONFIRMED


def classify_pdf_source(*, page_verified: bool) -> tuple[SourceType, SourceQuality]:
    """An uploaded PDF's publisher is not knowable in general (Orchid
    Island could upload anything), so quality here is a proxy for how well
    this specific event's claim could actually be traced back into the
    document: CREDIBLE_SECONDARY when the page it came from was verified
    against the real page count, EARLY_UNCONFIRMED when it could not be
    pinned to a real page at all."""
    return SourceType.PDF, SourceQuality.CREDIBLE_SECONDARY if page_verified else SourceQuality.EARLY_UNCONFIRMED

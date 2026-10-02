"""Tests for src/services/source_classification.py (2026-09-24 addition).
Pure lookup logic, no network/LLM involved -- these confirm the mapping is
what the docstrings there claim, and that unknown input degrades honestly
rather than crashing or silently upgrading."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.event import SourceQuality, SourceType
from src.services.source_classification import (
    classify_pdf_source,
    classify_web_source,
    classify_youtube_source,
)


def test_government_domain_is_primary():
    assert classify_web_source("https://www.imf.org/en/News/some-article") == (
        SourceType.GOVERNMENT, SourceQuality.PRIMARY,
    )


def test_gov_tld_is_primary():
    assert classify_web_source("https://www.eia.gov/outlook") == (SourceType.GOVERNMENT, SourceQuality.PRIMARY)


def test_linkedin_is_primary():
    assert classify_web_source("https://www.linkedin.com/posts/acme-group_expansion") == (
        SourceType.LINKEDIN, SourceQuality.PRIMARY,
    )


def test_report_domain_is_credible_secondary():
    assert classify_web_source("https://www.knightfrank.com/research/morocco") == (
        SourceType.REPORT, SourceQuality.CREDIBLE_SECONDARY,
    )


def test_business_media_domain_is_credible_secondary():
    assert classify_web_source("https://www.bloomberg.com/news/articles/x") == (
        SourceType.BUSINESS_MEDIA, SourceQuality.CREDIBLE_SECONDARY,
    )


def test_recognized_news_outlet_is_credible_secondary():
    assert classify_web_source("https://www.reuters.com/world/africa/x") == (
        SourceType.NEWS, SourceQuality.CREDIBLE_SECONDARY,
    )


def test_unrecognized_domain_falls_back_to_news_not_a_crash():
    result = classify_web_source("https://some-outlet-not-in-any-list.example.com/story")
    assert result == (SourceType.NEWS, SourceQuality.CREDIBLE_SECONDARY)


def test_malformed_url_is_not_verified_rather_than_crashing():
    assert classify_web_source("not a url at all") == (SourceType.OTHER, SourceQuality.NOT_VERIFIED)


def test_youtube_is_always_early_unconfirmed():
    """No curated allowlist for YouTube (see MonitoringAgentConfig's own
    docstring), so this must never be upgraded to a stronger tier on a
    guess about which channel it happened to be."""
    assert classify_youtube_source() == (SourceType.OTHER, SourceQuality.EARLY_UNCONFIRMED)


def test_pdf_with_verified_page_is_credible_secondary():
    assert classify_pdf_source(page_verified=True) == (SourceType.PDF, SourceQuality.CREDIBLE_SECONDARY)


def test_pdf_without_verified_page_is_early_unconfirmed():
    assert classify_pdf_source(page_verified=False) == (SourceType.PDF, SourceQuality.EARLY_UNCONFIRMED)

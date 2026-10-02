"""Generalized monitoring agent (Phase 2 of the roadmap): one implementation,
configured per source category, so adding a new agent is a config change,
not new code (NFR: maintainability, Cahier des Charges).

Two source types share this one function:
  - "web" (the original 5 agents): web_search -> fetch_page ->
    extract_content -> llm_client.summarize_event -> Event.
  - "youtube" (2026-09-16 addition): youtube_search -> fetch_transcript ->
    llm_client.summarize_event -> Event. Same shape, same tool-grounded,
    never-fabricates-from-memory contract, same per-item "one bad source
    doesn't crash the run" error handling -- only the retrieval step
    differs, because a video's real content is its transcript, not an HTML
    page. See src/tools/youtube_search.py and
    src/tools/youtube_transcript.py for why each is built the way it is,
    including the honest caveat that the transcript tool is not an
    official, contractually-supported Google endpoint.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Optional

from src.config import settings
from src.errors import MissingConfigurationError
from src.models import Event, EventEntities
from src.services import llm_client
from src.services.source_classification import classify_web_source, classify_youtube_source
from src.tools import extract_content, fetch_page, fetch_transcript, web_search, youtube_search

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonitoringAgentConfig:
    name: str
    source_category: str  # passed through to web_search() for logging/filtering
    default_query: str
    default_sectors: tuple[str, ...] = ()
    # "web" (default) or "youtube" -- selects which retrieval pipeline
    # run_monitoring_agent uses below. Everything else on this dataclass
    # (name, default_query, default_sectors, recency_days) means the same
    # thing for either type; source_domains is web-only (see its own
    # docstring).
    source_type: str = "web"
    # Real, named outlets to restrict search to (Tavily's include_domains).
    # Empty = unrestricted web search. See the module-level comment above
    # MONITORING_AGENTS for how/why this list was chosen for each agent.
    # Not used when source_type="youtube" -- YouTube's search API has no
    # equivalent include_domains restriction to a curated outlet list; it
    # searches the whole platform (see youtube_search.py's own docstring
    # for the region_code parameter, a different, not-yet-verified way to
    # narrow results).
    source_domains: tuple[str, ...] = ()
    # Restrict to the last N days via Tavily's news mode (web) or the
    # YouTube Data API's publishedAfter (youtube). None = provider default
    # (Tavily's relevance-ranked search across all indexed content; YouTube's
    # unrestricted relevance search). See the module-level comment above
    # MONITORING_AGENTS: this is a per-category judgment call verified
    # against the real API, not a blanket default -- except for the YouTube
    # agent's recency_days, which could NOT be verified against the real
    # API in the session that added it (no real YOUTUBE_API_KEY was
    # available then). Worth confirming with one real run once a key is
    # configured, the same way every other value in this file was checked.
    recency_days: Optional[int] = None


# The 5 V1 agent categories from the Concept & Architecture Report, Section 4,
# plus a 6th (YouTube) added 2026-09-16 at Orchid Island's request to catch
# video commentary and news coverage that a text-only web search misses.
# Adding a further agent (e.g. a Social & Sentiment Agent, flagged V2) means
# adding one more entry here — no other code changes.
#
# source_domains below are real, named, currently-operating outlets, picked
# for topical fit to each category and (for the MENA/Morocco and Real
# Estate agents especially) source credibility per the earlier "use other
# sources" pass — see knowledge_base/macro_morocco.md and
# knowledge_base/real_estate_market_snapshot.md for the same institutional
# sources (Bank Al-Maghrib, Knight Frank, W Hospitality Group) used there.
# Verified directly against the real Tavily API: restricting to these
# domains reliably returns a specific, real, fetchable article instead of a
# site's homepage or a category-listing page (which an unrestricted generic
# query sometimes returns instead — see
# reports/2026-09-10_automated_pipeline_run.md for a real example of that
# failure mode this list is meant to fix). This is a starting list, not a
# final one — README.md "What I need from you" item 4 is still open for you
# to review, add outlets you already subscribe to, or remove any you don't
# want cited.
#
# recency_days is likewise a real, tested judgment call, not a blanket
# default: for the two wire-service-style categories below (political,
# economic) and written commentary, Tavily's news mode + a 7-day window
# reliably returned same-week, dated articles. For MENA/Morocco and real
# estate, the same news-mode restriction returned zero or off-topic results
# (these domains' relevant content isn't well covered by Tavily's news
# index) — plain relevance-ranked search across all indexed content found
# better, more specific, still-recent real articles for those two, so
# recency_days is left at its default (None/off) there.
MONITORING_AGENTS: list[MonitoringAgentConfig] = [
    # 2026-09-11 addition: broadened to more international outlets per Orchid
    # Island's request to catch world events (e.g. wars/conflicts) with a
    # transmission channel into Marrakech real estate (safe-haven capital
    # flows, energy costs, tourist-source-market risk). NOTE: unlike the
    # original list above, these specific domains could not be re-verified
    # against the live Tavily API in the session that added them (outbound
    # access to api.tavily.com was blocked by that session's own sandbox
    # network policy) -- they are real, major, currently-operating
    # international outlets, but should be confirmed with one real
    # POST /run-digest the way every other domain in this file was.
    MonitoringAgentConfig(
        name="Global Political News Agent",
        source_category="global_political",
        default_query="diplomatic tensions conflict sanctions negotiations this week",
        source_domains=(
            "reuters.com", "apnews.com", "aljazeera.com", "foreignpolicy.com", "bbc.com",
            "cnn.com", "theguardian.com", "nytimes.com", "dw.com", "france24.com",
            "economist.com", "middleeasteye.net", "ft.com",
        ),
        recency_days=7,
    ),
    # 2026-09-11 addition: added primary energy/commodity sources -- the
    # concrete channel through which a war/conflict abroad reaches Moroccan
    # real estate prices is via oil/energy import costs and construction
    # material costs (Morocco is a net energy importer -- see
    # knowledge_base/macro_morocco.md's note on oil-price risk to the
    # current account). Same live-verification caveat as above applies.
    MonitoringAgentConfig(
        name="Global Economic & Markets Agent",
        source_category="global_economic",
        default_query="central bank interest rate decision commodity market outlook",
        source_domains=(
            "reuters.com", "bloomberg.com", "imf.org", "worldbank.org", "tradingeconomics.com",
            "eia.gov", "spglobal.com",
            # 2026-09-16 addition, live-verified against the real Tavily API
            # with this exact query: both returned real, dated articles (a
            # same-week ECB rate-hike story from each). ft.com also closes a
            # pre-existing gap -- it was already in the Political agent's
            # list above despite being primarily financial, but missing here.
            "ft.com", "cnbc.com",
        ),
        recency_days=7,
    ),
    MonitoringAgentConfig(
        name="Expert Commentary Agent",
        source_category="expert_commentary",
        default_query="economic outlook analysis commentary",
        # Written analysis/commentary outlets rather than podcast platforms:
        # a podcast's own page is usually an episode list or player embed
        # (little to no extractable text — see the 2026-09-10 real run),
        # while these publish full written pieces that extract_content()
        # can actually work with.
        source_domains=(
            "project-syndicate.org", "voxeu.org", "brookings.edu",
            # 2026-09-16 addition, live-verified against the real Tavily API
            # with this exact query: both returned real, full written
            # analysis pieces (McKinsey's Global Economics Intelligence
            # series, CFR's Iran-war regional-impact commentary).
            "cfr.org", "mckinsey.com",
        ),
        recency_days=7,
    ),
    MonitoringAgentConfig(
        name="Regional MENA & Morocco Agent",
        source_category="regional_mena_morocco",
        default_query="Morocco economy tourism real estate news",
        default_sectors=("tourism",),
        source_domains=(
            "en.hespress.com", "moroccoworldnews.com", "medias24.com", "thearabweekly.com",
            # 2026-09-16 addition, live-verified against the real Tavily API
            # with this exact query: all three returned real, specific,
            # Morocco-focused articles (Morocco IMF growth forecasts, the
            # Airbnb/vacation-rental tourism-regulation story, North Africa
            # tourism comparisons) rather than a homepage. Tried but not
            # kept -- no results for this query at time of testing:
            # leseco.ma, telquel.ma, yabiladi.com, mapnews.ma (worth
            # retrying later with a different query; a source returning
            # nothing for one query is not the same as a bad source).
            "arabnews.com", "thenationalnews.com", "en.le360.ma",
        ),
    ),
    MonitoringAgentConfig(
        name="Real Estate Sector Agent",
        source_category="real_estate_sector",
        default_query="Morocco Marrakech hospitality real estate investment report",
        default_sectors=("real_estate",),
        source_domains=(
            "knightfrank.com", "knightfrank.co.uk", "jll.com", "cbre.com", "hotelnewsnow.com",
            # 2026-09-16 addition, live-verified against the real Tavily API
            # with this exact query: globalpropertyguide.com returned a
            # Morocco-specific residential market analysis, skift.com
            # returned real hospitality-investment articles (including one
            # specifically on Morocco investment beyond Casablanca and
            # Marrakech). NOTE: the first version of this same test, run
            # with a 5-domain include_domains list that also had
            # savills.com/colliers.com/hospitalitynet.org (which returned
            # nothing for this query), came back with 3 Wikipedia results
            # that were never requested -- see src/tools/web_search.py's
            # 2026-09-16 docstring note and _matches_included_domain(),
            # added the same day, which now drops any such off-list result
            # rather than trusting Tavily to honor include_domains when few
            # of the requested domains have current matches. Tried but not
            # kept -- no results for this query at time of testing:
            # savills.com, colliers.com, hospitalitynet.org (same caveat as
            # above: worth retrying with a different query later).
            "globalpropertyguide.com", "skift.com",
        ),
    ),
    # 2026-09-16 addition, at Orchid Island's request: video coverage (news
    # segments, interviews, market-analysis channels) that a text-only web
    # search never sees, even when the same outlets publish it. One agent
    # covering both real estate and the tourism/economy backdrop that
    # drives it, rather than splitting YouTube across all 5 categories --
    # narrower in scope for now, can be split later if it proves worth it.
    # source_domains is deliberately empty here (see the field's own
    # docstring: YouTube search has no include_domains equivalent to
    # restrict to a curated outlet list the way Tavily does).
    # 2026-09-17: tightened from recency_days=14 to 7 after the first real
    # run against the live API came back empty. 2026-09-21: widened again to
    # 30 after a real, unfiltered run (see _test_youtube_diagnostic.py's
    # output) showed the actual publishing cadence for this specific query:
    # of the 10 real videos returned, only 1 fell in the last 7 days, and
    # only 4 fell in the last 30 -- the rest went back to April, March,
    # February, and December 2025. This niche topic (Marrakech real estate
    # investment specifically, in French/Arabic-language YouTube content)
    # genuinely gets covered in bursts every few weeks, not daily, so a
    # 7-day window would leave the digest empty on most days for a real,
    # honest reason (nothing new to show), not a bug. 30 days is a better
    # match for the real cadence: it reliably surfaces something without
    # going so stale that a "today's digest" entry is actually months old.
    # order="relevance" (not "date") still applies on top of this window --
    # YouTube can surface a slightly older upload within it if it matches
    # the query better, since a commentary/analysis video often revisits an
    # event that happened a bit earlier. Revisit again if real runs show 30
    # is still too loose (too many stale-feeling results) or still too
    # tight (too many empty days).
    MonitoringAgentConfig(
        name="YouTube Video Monitoring Agent",
        source_category="youtube_video",
        source_type="youtube",
        default_query="Marrakech Morocco real estate market investment analysis",
        default_sectors=("real_estate", "tourism"),
        recency_days=30,
    ),
]


def _parse_published_date(value: Optional[str]) -> Optional[date]:
    """Real sources return dates in more than one real format — e.g.
    extract_content()'s own detection yields ISO ("2026-09-04"), while
    Tavily's news-mode results come back as RFC 2822 ("Fri, 04 Sep 2026
    20:34:06 GMT"). Found via a real run (a genuine bug, not a hypothetical
    one): the RFC 2822 form failed Event's date validation and silently
    dropped every event from the three news-mode agents. Try both real
    formats; if neither parses, return None (an honest "unknown date")
    rather than crashing the whole event over a date string quirk.

    The YouTube Data API's publishedAt ("2026-09-04T12:00:00Z", RFC 3339)
    parses through the same ISO path as the first branch below -- no third
    format needed."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError):
        logger.warning("could not parse published date %r, leaving unset", value)
        return None


def run_monitoring_agent(config: MonitoringAgentConfig, max_results: int = 3) -> list[Event]:
    """Independent per-agent run (FR-02, FR-04): receives no state from any
    other agent. Returns [] on a genuine per-call/per-item failure rather
    than raising, so one source outage never crashes the daily run (FR-14).

    MissingConfigurationError is different: it means a required credential
    (WEB_SEARCH_API_KEY / YOUTUBE_API_KEY, LLM_API_KEY) isn't set at all.
    That is not "this source had an outage today" — it's "this system
    cannot run for real right now" — so it is deliberately NOT caught here.
    It propagates up to the orchestrator node, which records it as a
    failed step with the real error, instead of being swallowed into a
    silent "0 events found."
    """
    if config.source_type == "youtube":
        return _run_youtube_agent(config, max_results)
    return _run_web_agent(config, max_results)


def _run_web_agent(config: MonitoringAgentConfig, max_results: int) -> list[Event]:
    """web_search -> fetch_page -> extract_content -> summarize_event. See
    run_monitoring_agent's docstring for the shared error-handling contract."""
    events: list[Event] = []
    try:
        results = web_search(
            config.default_query,
            source_category=config.source_category,
            max_results=max_results,
            include_domains=list(config.source_domains) or None,
            recency_days=config.recency_days,
        )
    except MissingConfigurationError:
        raise
    except Exception as exc:
        logger.error("%s: web_search failed: %s", config.name, exc)
        return events

    for result in results:
        try:
            page = fetch_page(result.url)
            if page is None:
                logger.warning("%s: could not fetch %s, skipping", config.name, result.url)
                continue
            content = extract_content(page.html)
            summary_fields = llm_client.summarize_event(
                agent_name=config.name,
                article_title=content.title or result.title,
                article_text=content.main_text,
                source_url=result.url,
            )
            # 2026-09-17: a "low" relevance judgment used to only change the
            # colored pill shown in the report -- the item still made it
            # into the daily digest either way. At Orchid Island's request,
            # "low" now means what it says: the AI read the real article
            # and judged it not actually useful for real-estate/tourism
            # monitoring, so skip it here rather than surface noise. This
            # is the same LLM call already made for every item, just acted
            # on -- no extra cost, no separate filtering step.
            if summary_fields["relevance_to_real_estate"] == "low":
                logger.info(
                    "%s: skipping %s, judged low relevance", config.name, result.url
                )
                continue
            source_type, source_quality = classify_web_source(result.url)
            event = Event(
                id=str(uuid.uuid4()),
                agent=config.name,
                headline=content.title or result.title,
                summary=summary_fields["summary"],
                entities=EventEntities(sectors=list(config.default_sectors)),
                sentiment=summary_fields["sentiment"],
                relevance_to_real_estate=summary_fields["relevance_to_real_estate"],
                confidence=summary_fields["confidence"],
                source_url=result.url,
                source_name=config.name,
                published_at=_parse_published_date(content.detected_publish_date or result.published_date),
                agent_interpretation=summary_fields["agent_interpretation"],
                retrieval_id=str(uuid.uuid4()),
                source_type=source_type,
                source_quality=source_quality,
            )
            events.append(event)
        except MissingConfigurationError:
            # Not a per-article failure — LLM_API_KEY isn't set at all, so
            # every remaining article would fail the same way. Let it
            # propagate rather than silently skipping every article.
            raise
        except Exception as exc:  # one bad article must not kill the whole agent run
            logger.error("%s: failed processing %s: %s", config.name, result.url, exc)
            continue

    logger.info("%s produced %d events", config.name, len(events))
    return events


def _run_youtube_agent(config: MonitoringAgentConfig, max_results: int) -> list[Event]:
    """youtube_search -> fetch_transcript -> summarize_event. Same shape and
    same error-handling contract as _run_web_agent above: a video's real
    content (its transcript) stands in for a fetched page's extracted
    text; everything downstream (the LLM summarization call, the Event it
    builds) is identical."""
    events: list[Event] = []
    try:
        results = youtube_search(
            config.default_query,
            max_results=max_results,
            recency_days=config.recency_days,
        )
    except MissingConfigurationError:
        raise
    except Exception as exc:
        logger.error("%s: youtube_search failed: %s", config.name, exc)
        return events

    for result in results:
        try:
            transcript = fetch_transcript(result.video_id)
            if transcript is None:
                logger.warning("%s: no usable transcript for %s, skipping", config.name, result.url)
                continue
            summary_fields = llm_client.summarize_event(
                agent_name=config.name,
                article_title=result.title,
                article_text=transcript.text,
                source_url=result.url,
            )
            # See _run_web_agent's identical check for why: a video whose
            # real transcript the AI judges "low" relevance (e.g. it only
            # mentions Marrakech in passing, or isn't really about real
            # estate/tourism/investment) is skipped rather than shown --
            # Orchid Island's report should only carry videos that actually
            # relate to and benefit the platform's own content, not every
            # video the keyword search happened to match.
            if summary_fields["relevance_to_real_estate"] == "low":
                logger.info(
                    "%s: skipping %s, judged low relevance", config.name, result.url
                )
                continue
            source_type, source_quality = classify_youtube_source()
            event = Event(
                id=str(uuid.uuid4()),
                agent=config.name,
                headline=result.title,
                summary=summary_fields["summary"],
                entities=EventEntities(sectors=list(config.default_sectors)),
                sentiment=summary_fields["sentiment"],
                relevance_to_real_estate=summary_fields["relevance_to_real_estate"],
                confidence=summary_fields["confidence"],
                source_url=result.url,
                source_name=f"{config.name} — {result.channel_title}" if result.channel_title else config.name,
                published_at=_parse_published_date(result.published_date),
                agent_interpretation=summary_fields["agent_interpretation"],
                retrieval_id=str(uuid.uuid4()),
                source_type=source_type,
                source_quality=source_quality,
            )
            events.append(event)
        except MissingConfigurationError:
            raise
        except Exception as exc:  # one bad video must not kill the whole agent run
            logger.error("%s: failed processing %s: %s", config.name, result.url, exc)
            continue

    logger.info("%s produced %d events", config.name, len(events))
    return events

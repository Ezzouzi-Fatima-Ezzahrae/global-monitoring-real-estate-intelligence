"""Tests for the opportunity-hook builder (2026-09-24 addition,
src/agents/judge_agent.py's should_generate_hook/build_hook). No LLM call
involved -- these are pure functions over already-built Event/
ImpactAssessment objects, so tests just construct those directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.judge_agent import build_hook, should_generate_hook
from src.models.event import Event, EventEntities, SourceQuality, SourceType
from src.models.impact import ImpactAssessment


def _event(**overrides) -> Event:
    defaults = dict(
        id="e1", agent="Real Estate Sector Agent", headline="Foreign hotel group visits Marrakech",
        summary="A foreign hospitality group's executives toured several Marrakech sites this week.",
        entities=EventEntities(), sentiment="positive", relevance_to_real_estate="high", confidence=0.7,
        source_url="https://www.hotelnewsnow.com/some-article", source_name="Real Estate Sector Agent",
        agent_interpretation="Could signal a future hotel development.", retrieval_id="r1",
        source_type=SourceType.BUSINESS_MEDIA, source_quality=SourceQuality.CREDIBLE_SECONDARY,
    )
    defaults.update(overrides)
    return Event(**defaults)


def _impact(**overrides) -> ImpactAssessment:
    defaults = dict(
        event_id="e1", sector_or_market_affected="hospitality / hotel development", direction="positive",
        magnitude="high", confidence=0.8, time_horizon="short_term",
        rationale="A real hotel group scouting sites is a plausible precursor to a land or property search.",
        recommended_action="Identify the group's local representative and monitor for a site search.",
    )
    defaults.update(overrides)
    return ImpactAssessment(**defaults)


def test_should_generate_hook_for_a_real_positive_high_magnitude_signal():
    assert should_generate_hook(_event(), _impact()) is True


def test_should_not_generate_hook_for_low_relevance():
    assert should_generate_hook(_event(relevance_to_real_estate="low"), _impact()) is False


def test_should_not_generate_hook_for_a_pure_risk():
    assert should_generate_hook(_event(), _impact(direction="negative")) is False


def test_should_not_generate_hook_for_low_magnitude():
    assert should_generate_hook(_event(), _impact(magnitude="low")) is False


def test_should_not_generate_hook_when_contested():
    assert should_generate_hook(_event(), _impact(contested=True, confidence=0.4)) is False


def test_should_not_generate_hook_below_confidence_floor():
    assert should_generate_hook(_event(), _impact(confidence=0.2)) is False


def test_hotel_keyword_picks_hotel_template():
    hook = build_hook(_event(), _impact())
    assert "HOTEL" in hook.headline
    assert "\U0001F6A8" in hook.headline  # the 🚨 marker, present on every hook


def test_early_signal_headline_uses_hedged_language_by_default():
    # source_quality is CREDIBLE_SECONDARY, not PRIMARY, so even a
    # high-confidence assessment must stay an early signal, hedged wording.
    hook = build_hook(_event(source_quality=SourceQuality.CREDIBLE_SECONDARY), _impact(confidence=0.9))
    assert hook.stage == "early_signal"
    assert "MAY BE" in hook.headline


def test_confirmed_only_when_primary_source_and_high_confidence():
    hook = build_hook(_event(source_quality=SourceQuality.PRIMARY), _impact(confidence=0.9))
    assert hook.stage == "confirmed"
    assert "MAY BE" not in hook.headline


def test_primary_source_but_low_confidence_stays_early_signal():
    hook = build_hook(_event(source_quality=SourceQuality.PRIMARY), _impact(confidence=0.5))
    assert hook.stage == "early_signal"


def test_confidence_label_tracks_the_real_impact_confidence():
    assert build_hook(_event(), _impact(confidence=0.9)).confidence_label == "high"
    assert build_hook(_event(), _impact(confidence=0.5)).confidence_label == "medium"
    assert build_hook(_event(), _impact(confidence=0.05, magnitude="high")).confidence_label == "low"


def test_why_it_matters_and_suggested_action_are_copied_verbatim_never_invented():
    impact = _impact(rationale="Exact real rationale text.", recommended_action="Exact real action text.")
    hook = build_hook(_event(), impact)
    assert hook.why_it_matters == "Exact real rationale text."
    assert hook.suggested_action == "Exact real action text."


def test_evidence_is_built_only_from_real_event_fields():
    event = _event(summary="Real summary text.", agent_interpretation="Real interpretation text.")
    hook = build_hook(event, _impact())
    assert "Real summary text." in hook.evidence
    assert "Real interpretation text." in hook.evidence


def test_industrial_keyword_picks_industrial_requirement_keys():
    # Keys, not display text -- the console's static i18n layer turns these
    # into EN/FR/AR labels (see i18n.js's requirementLabel), so an AI
    # translation call is never needed for this fixed vocabulary.
    hook = build_hook(_event(), _impact(sector_or_market_affected="industrial / logistics land"))
    assert "industrial_site" in hook.potential_requirements


def test_unmatched_sector_falls_back_to_default_requirement_keys():
    hook = build_hook(_event(), _impact(sector_or_market_affected="something unrelated entirely"))
    assert hook.potential_requirements == ["land", "local_partner"]

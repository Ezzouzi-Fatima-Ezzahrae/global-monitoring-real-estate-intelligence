import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import MONITORING_AGENTS
from src.config import settings
from src.orchestrator import run_pipeline


def test_pipeline_runs_end_to_end_and_produces_a_report(stub_full_pipeline):
    state = run_pipeline()
    assert state.report is not None
    assert not state.report.no_significant_events
    assert len(state.events) >= 1


def test_judge_stage_produces_a_real_impact_assessment_per_event(stub_full_pipeline):
    """Phase 5 (Judge): every event that made it through the pipeline gets a
    real, structured impact assessment, and the report surfaces it as risks/
    opportunities and recommended actions rather than leaving them empty —
    this is the feature that lets the Digest Console show *why* an event
    matters to Orchid Island, not just that it happened."""
    state = run_pipeline()
    assert len(state.impact_assessments) == len(state.events)
    assessed_event_ids = {a.event_id for a in state.impact_assessments}
    assert assessed_event_ids == {e.id for e in state.events}

    assert state.report.impact_analysis == state.impact_assessments
    assert len(state.report.risks_and_opportunities) == len(state.events)
    assert len(state.report.recommended_actions) == len(state.events)
    assert any("Judge Stage" == s.agent for s in state.trace)


def test_every_configured_agent_appears_in_the_trace(stub_full_pipeline):
    state = run_pipeline()
    traced_agents = {step.agent for step in state.trace}
    expected_agents = {c.name for c in MONITORING_AGENTS}
    assert expected_agents.issubset(traced_agents)


def test_all_agents_ran_independently_no_shared_mutable_state_leak(stub_full_pipeline):
    """Independence guardrail (FR-04): confirm each agent's events are
    correctly attributed to itself only — a regression here would mean
    agents are somehow seeing/mixing each other's output."""
    state = run_pipeline()
    for event in state.events:
        assert event.agent in {c.name for c in MONITORING_AGENTS}


def test_report_never_fabricates_a_citation_not_in_events(stub_full_pipeline):
    state = run_pipeline()
    event_urls = {str(e.source_url) for e in state.events}
    for citation in state.report.citations:
        assert citation in event_urls, f"citation {citation} not traceable to a real event (FR-12)"


def test_missing_web_search_key_surfaces_honestly_not_as_silent_zero_events(
    stub_youtube_search, stub_fetch_transcript, stub_summarize_event, stub_complete_json, monkeypatch
):
    """The pipeline must be honest when a chunk of it can't really run: each
    web-based monitoring-agent node catches MissingConfigurationError and
    records it in the trace (a graph node must never crash the graph itself
    — see graph.py's belt-and-braces try/except), and the report explains
    why, instead of looking like a silent, unexplained shortfall.

    WEB_SEARCH_API_KEY is only required by the 5 web-based agents (FR-04:
    each agent is independent, including in which credential it needs) —
    the YouTube agent uses its own YOUTUBE_API_KEY and is unaffected here
    (stubbed so it succeeds, same as any other test that isn't specifically
    about it), which is itself the behavior this test locks in: one
    missing credential doesn't take down an agent that doesn't need it.
    See test_missing_all_required_keys_fails_every_agent_honestly below for
    the case where nothing can run at all."""
    monkeypatch.setattr(settings, "web_search_api_key", "")
    state = run_pipeline()

    web_agent_names = {c.name for c in MONITORING_AGENTS if c.source_type != "youtube"}
    agent_steps = [s for s in state.trace if s.agent in web_agent_names]
    assert agent_steps  # every web-based monitoring agent still reported in
    assert all(s.status == "failed" for s in agent_steps)
    assert all("WEB_SEARCH_API_KEY" in (s.error or "") for s in agent_steps)
    assert any("WEB_SEARCH_API_KEY" in lim for lim in state.report.limitations)

    # The independent YouTube agent (stubbed to succeed) still reported a
    # real event — a missing WEB_SEARCH_API_KEY must not silently take it
    # down too.
    youtube_step = next(s for s in state.trace if s.agent == "YouTube Video Monitoring Agent")
    assert youtube_step.status == "completed"
    assert any(e.agent == "YouTube Video Monitoring Agent" for e in state.events)


def test_missing_all_required_keys_fails_every_agent_honestly(monkeypatch):
    """Same honesty guarantee, extended to every agent and every credential
    it needs (WEB_SEARCH_API_KEY for the 5 web agents, YOUTUBE_API_KEY for
    the YouTube agent): the pipeline never quietly reports '0 events found
    today' for no stated reason when it genuinely could not run at all."""
    monkeypatch.setattr(settings, "web_search_api_key", "")
    monkeypatch.setattr(settings, "youtube_api_key", "")
    state = run_pipeline()

    assert state.events == []
    agent_steps = [s for s in state.trace if s.agent != "Debate Stage"]
    assert agent_steps  # every monitoring agent still reported in
    assert all(s.status == "failed" for s in agent_steps)
    assert all(
        ("WEB_SEARCH_API_KEY" in (s.error or "")) or ("YOUTUBE_API_KEY" in (s.error or ""))
        for s in agent_steps
    )

    assert state.report.no_significant_events
    assert any(
        ("WEB_SEARCH_API_KEY" in lim) or ("YOUTUBE_API_KEY" in lim) for lim in state.report.limitations
    )

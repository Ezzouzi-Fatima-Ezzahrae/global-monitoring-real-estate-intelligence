"""LangGraph orchestrator — V1+Phase 3+Phase 4+Phase 5 scope (see the roadmap).

Current graph:

    START -> [6 monitoring agent nodes, run in parallel] -> collect
           -> debate -> judge -> format_report -> END

Debate (Phase 3) and Judge (Phase 5, first version) are implemented
(src/agents/debate_agent.py, src/agents/judge_agent.py) — debate is a
bounded, ≤3-round adversarial review run by two independently-configured
LLM voices; judge turns each event plus its debate outcome into a
structured, sourced impact assessment (src/models/impact.py). As of
2026-09-15, Judge also draws on Orchid Island's own company data and the
curated knowledge base (Phase 4 RAG, src/services/knowledge_base.py) —
real, lexical (BM25 keyword) retrieval over knowledge_base/, not
embeddings, since no embedding endpoint is configured anywhere in this
project. Retrieval runs inside the judge node itself (no separate graph
node needed) — Judge's insertion point (after debate, before
format_report) was already reserved, so wiring RAG in did not require
rewriting anything that was already here (NFR: maintainability).
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Optional

from langgraph.graph import END, StateGraph

from src.agents import MONITORING_AGENTS, build_hook, run_debate, run_judge, run_monitoring_agent, should_generate_hook
from src.models import DailyReport, PipelineState
from src.models.debate import DebateStatus
from src.models.event import Event
from src.models.impact import ImpactAssessment
from src.models.state import AgentStep

logger = logging.getLogger(__name__)


def _make_agent_node(config):
    """Returns a LangGraph node function bound to one agent config. Each
    node reads nothing from state but run_date, and writes only its own
    events + one trace entry — independence enforced structurally (FR-04),
    the same pattern as the fact-checking project's Research/Counter-
    Evidence agents."""

    def node(state: PipelineState) -> dict:
        start = time.time()
        try:
            events = run_monitoring_agent(config)
            status = "completed"
            error = None
        except Exception as exc:  # belt-and-braces: run_monitoring_agent already
            # catches internally, but a node must never raise into the graph
            events, status, error = [], "failed", str(exc)
            logger.error("%s node failed: %s", config.name, exc)

        step = AgentStep(
            agent=config.name,
            status=status,
            duration_ms=int((time.time() - start) * 1000),
            error=error,
        )
        # LangGraph merges dict returns into state; events/trace are lists
        # so we return only the increment, not the full accumulated state.
        return {"events": events, "trace": [step]}

    return node


def _collect_node(state: PipelineState) -> dict:
    """Confirms all monitoring agents have reported in before debate runs."""
    logger.info("collect_node: %d total events from %d agent runs", len(state.events), len(state.trace))
    return {}


def _debate_node(state: PipelineState) -> dict:
    """Phase 3: bounded adversarial review of everything collect_node saw.
    Runs as its own graph step (after every agent has reported in, before
    the report is formatted) so debate always sees the full day's events at
    once — see src/agents/debate_agent.py for the round-by-round protocol."""
    start = time.time()
    try:
        debate_log = run_debate(state.events)
        status, error = "completed", None
    except Exception as exc:  # belt-and-braces: run_debate already catches internally
        debate_log, status, error = None, "failed", str(exc)
        logger.error("debate node failed: %s", exc)
    step = AgentStep(agent="Debate Stage", status=status, duration_ms=int((time.time() - start) * 1000), error=error)
    return {"debate_log": debate_log, "trace": [step]}


def _judge_node(state: PipelineState) -> dict:
    """Phase 5: turns each event, together with its debate outcome, into a
    structured, sourced impact assessment — see src/agents/judge_agent.py
    for the model call (now including Phase 4 RAG retrieval per event) and
    the FR-08 confidence-ceiling enforcement. Skipped with no trace entry
    when there are no events to assess (same reasoning as collect/debate
    having nothing to do on an empty day) — this keeps a zero-events run's
    trace exactly as honest as it was before this stage existed, rather
    than adding a hollow 'completed, assessed 0 events' entry that implies
    work was done."""
    if not state.events:
        return {}
    start = time.time()
    try:
        assessments = run_judge(state.events, state.debate_log)
        status, error = "completed", None
    except Exception as exc:  # belt-and-braces: run_judge already catches internally
        assessments, status, error = [], "failed", str(exc)
        logger.error("judge node failed: %s", exc)
    step = AgentStep(agent="Judge Stage", status=status, duration_ms=int((time.time() - start) * 1000), error=error)
    return {"impact_assessments": assessments, "trace": [step]}


# 2026-09-21, at Orchid Island's request: rank events so the report reads
# top-down by what actually matters most, using the impact assessment
# Judge already computes for every event rather than a separate AI call.
# Weights are deliberately simple/explainable (see
# src/models/report.py's PRIORITY_EXPLANATION, which is shown to Orchid
# Island directly and must stay true to what this actually does): a bigger
# likely effect, higher confidence in that assessment, and something that
# matters sooner all push an event's rank up.
_MAGNITUDE_WEIGHT = {"low": 1, "medium": 2, "high": 3}
_HORIZON_WEIGHT = {"medium_term": 1, "short_term": 2, "immediate": 3}
_RELEVANCE_WEIGHT = {"low": 1, "medium": 2, "high": 3}
_CONTESTED_PENALTY = 0.5  # a contested assessment is real signal, just less trustworthy -- rank it lower, never drop it


def _impact_score(impact: ImpactAssessment) -> float:
    magnitude = impact.magnitude if isinstance(impact.magnitude, str) else impact.magnitude.value
    horizon = impact.time_horizon if isinstance(impact.time_horizon, str) else impact.time_horizon.value
    score = _MAGNITUDE_WEIGHT.get(magnitude, 1) * impact.confidence * _HORIZON_WEIGHT.get(horizon, 1)
    if impact.contested:
        score *= _CONTESTED_PENALTY
    return score


def _priority_sort_key(event: Event, impact: Optional[ImpactAssessment]) -> tuple[int, float]:
    """Returns (has_assessment, score): every event WITH a real Judge
    impact assessment outranks every event WITHOUT one (Judge failed for
    that one item, or the whole stage didn't run) -- among assessed
    events, ranked by _impact_score. An unassessed event still appears
    (FR-15: never drop a real event), falling back to its own relevance/
    confidence so its relative order isn't arbitrary."""
    if impact is not None:
        return (1, _impact_score(impact))
    relevance = event.relevance_to_real_estate
    relevance = relevance if isinstance(relevance, str) else relevance.value
    return (0, _RELEVANCE_WEIGHT.get(relevance, 1) * event.confidence)


def _format_report_node(state: PipelineState) -> dict:
    """V1+Phase3+Phase4+Phase5 report: lists what each independent agent
    found, the debate outcome per event, and a real per-event impact
    assessment turned into report-level risks, opportunities and
    recommended actions — grounded, where retrieval found a real match, in
    Orchid Island's own knowledge base rather than general knowledge alone.
    Judge's own honest scope limit (lexical, not semantic, retrieval; a
    small and still-growing knowledge base) is carried into the report's
    limitations rather than glossed over."""
    events = state.events
    if not events:
        failed_steps = [s for s in state.trace if s.status == "failed" and s.error]
        if failed_steps:
            # Be honest about *why* — a missing credential (MissingConfigurationError's
            # message names the exact .env variable) reads very differently from a
            # source that was genuinely unreachable today. Don't flatten both into the
            # same generic "check source availability" line.
            distinct_errors = list(dict.fromkeys(s.error for s in failed_steps))
            limitations = [
                f"No monitoring agent returned any events — {len(failed_steps)} of {len(state.trace)} agent run(s) "
                "failed. Reported error(s): " + " | ".join(distinct_errors)
            ]
        else:
            limitations = ["No monitoring agent returned any events — all ran without error but found nothing today."]
        report = DailyReport(
            report_date=dt.date.today(),
            headline="No events retrieved today.",
            no_significant_events=True,
            limitations=limitations,
        )
        return {"report": report}

    high_relevance = [e for e in events if e.relevance_to_real_estate in ("high", "medium")]
    debate_log = state.debate_log
    impact_assessments = state.impact_assessments

    # 2026-09-21: rank events (see _priority_sort_key above). Mutates each
    # Event's priority_rank field in place -- not returned as a new
    # "events" state update, since PipelineState.events uses an
    # operator.add reducer (see src/models/state.py) that would append
    # rather than replace, duplicating every event. Mutating the field on
    # the existing objects sidesteps that entirely and is picked up
    # wherever these same Event objects are serialized later (the API
    # response, run persistence, PDF/notification exports).
    impact_by_event_id = {ia.event_id: ia for ia in impact_assessments}
    ranked_events = sorted(
        events, key=lambda e: _priority_sort_key(e, impact_by_event_id.get(e.id)), reverse=True
    )
    for rank, e in enumerate(ranked_events, start=1):
        e.priority_rank = rank
    events = ranked_events

    # 2026-09-24, at Orchid Island's request: turn the events that look like
    # a real business-development opportunity into a hook (see
    # src/agents/judge_agent.py's should_generate_hook/build_hook -- both
    # reuse only fields already computed above, no new model call). Same
    # in-place-mutation pattern as priority_rank just above, for the same
    # reason (PipelineState.events is an operator.add reducer).
    for e in events:
        impact = impact_by_event_id.get(e.id)
        if impact is not None and should_generate_hook(e, impact):
            e.hook = build_hook(e, impact)

    # 2026-09-16: once the YouTube agent introduced an independent
    # credential (YOUTUBE_API_KEY, separate from WEB_SEARCH_API_KEY), a new
    # state became reachable that wasn't before: SOME agents fail on a
    # missing credential while others still produce real events. Surface
    # that honestly here too, rather than letting a report with real events
    # silently omit that part of the sources behind it never ran.
    monitoring_agent_names = {c.name for c in MONITORING_AGENTS}
    failed_agent_steps = [
        s for s in state.trace if s.agent in monitoring_agent_names and s.status == "failed" and s.error
    ]

    limitations: list[str] = []
    if failed_agent_steps:
        distinct_errors = list(dict.fromkeys(s.error for s in failed_agent_steps))
        limitations.append(
            f"{len(failed_agent_steps)} of {len(monitoring_agent_names)} monitoring agent(s) did not run "
            "today — the events below are everything the remaining agent(s) could collect. Reported "
            "error(s): " + " | ".join(distinct_errors)
        )
    limitations.append(
        "RAG knowledge base (Phase 4) is live using real, lexical (BM25 keyword) retrieval over "
        "knowledge_base/ — not semantic/embedding-based, so it only surfaces a knowledge-base "
        "section when an event shares real vocabulary with it, and it will miss a genuinely "
        "relevant section that happens to use different wording. See knowledge_base/README.md "
        "for what is currently in the knowledge base and what is still missing."
    )
    debate_highlights: list[str] = []
    if debate_log is None:
        limitations.insert(0, "Debate stage did not produce a result this run — see the pipeline trace for the error.")
    else:
        contested_or_uncertain = [c for c in debate_log.events if c.status != DebateStatus.RESOLVED]
        by_id = {e.id: e for e in events}
        for c in debate_log.events:
            ev = by_id.get(c.event_id)
            label = ev.headline if ev else c.event_id
            debate_highlights.append(f"[{c.status.upper() if isinstance(c.status, str) else c.status.value.upper()}] {label} — {c.reason}")
        limitations.append(
            f"Debate stage ran {debate_log.round_count} round(s): {len(debate_log.events) - len(contested_or_uncertain)} "
            f"event(s) resolved, {len(contested_or_uncertain)} still contested/uncertain — see 'Debate Highlights' "
            "for specifics rather than treating every event as equally trustworthy."
        )

    # Judge (Phase 5): turn each impact assessment into report-level risks,
    # opportunities and recommended actions. A missing/failed Judge run is
    # reported honestly rather than silently leaving these lists empty.
    judge_step = next((s for s in state.trace if s.agent == "Judge Stage"), None)
    risks_and_opportunities: list[str] = []
    recommended_actions: list[str] = []
    if judge_step is not None and judge_step.status == "failed":
        limitations.insert(0, f"Judge stage did not produce impact assessments this run — {judge_step.error}")
    elif not impact_assessments:
        limitations.append(
            "Judge stage ran but produced no impact assessments this run (each event's individual "
            "assessment failed — see logs for details)."
        )
    else:
        limitations.append(
            "Judge stage (Phase 5) reasons from each event's own content, general real-estate/"
            "macroeconomic knowledge, and (Phase 4) whatever real, sourced material the knowledge "
            "base retrieval actually matched for that specific event — many events will still match "
            "nothing, since the knowledge base does not yet cover every property, deal or region "
            "Orchid Island cares about. Each assessment's supporting_evidence field lists exactly "
            "which knowledge-base sections (if any) were retrieved for it. Treat the sector/"
            "direction/magnitude calls below as informed market context, not company-specific "
            "financial advice."
        )
        by_id_events = {e.id: e for e in events}
        direction_label = {"positive": "Opportunity", "negative": "Risk", "mixed": "Watch", "neutral": "Note"}
        # Same ranking as the events above (_impact_score), not just raw
        # confidence, so "Risks & Opportunities" reads in the same priority
        # order as "Top Events" rather than a second, inconsistent ordering.
        for ia in sorted(impact_assessments, key=_impact_score, reverse=True):
            ev = by_id_events.get(ia.event_id)
            label = ev.headline if ev else ia.event_id
            flag = " (contested — confidence capped)" if ia.contested else ""
            direction = ia.direction if isinstance(ia.direction, str) else ia.direction.value
            magnitude = ia.magnitude if isinstance(ia.magnitude, str) else ia.magnitude.value
            horizon = ia.time_horizon if isinstance(ia.time_horizon, str) else ia.time_horizon.value
            line = (
                f"{direction_label.get(direction, 'Note')}: [{ia.sector_or_market_affected}] {label} — "
                f"{direction}/{magnitude}, confidence {ia.confidence:.2f}, {horizon.replace('_', ' ')}{flag}"
            )
            risks_and_opportunities.append(line)
            recommended_actions.append(f"{label}: {ia.recommended_action}")

    headline = (
        f"{len(events)} events collected across {len({e.agent for e in events})} sources; "
        f"{len(high_relevance)} flagged medium/high real-estate relevance."
    )
    report = DailyReport(
        report_date=dt.date.today(),
        headline=headline,
        top_events=events,
        debate_highlights=debate_highlights,
        impact_analysis=impact_assessments,
        risks_and_opportunities=risks_and_opportunities,
        recommended_actions=recommended_actions,
        limitations=limitations,
        citations=[str(e.source_url) for e in events],
    )
    return {"report": report}


def build_graph():
    graph = StateGraph(PipelineState)

    node_names = []
    for config in MONITORING_AGENTS:
        node_name = f"agent_{config.name.replace(' ', '_')}"
        graph.add_node(node_name, _make_agent_node(config))
        node_names.append(node_name)

    graph.add_node("collect", _collect_node)
    graph.add_node("debate", _debate_node)
    graph.add_node("judge", _judge_node)
    graph.add_node("format_report", _format_report_node)

    # Fan-out from START to every agent (parallel), fan-in to collect.
    # This is the structural mechanism (not just a prompt instruction) that
    # keeps every monitoring agent independent of every other one.
    for node_name in node_names:
        graph.set_entry_point(node_name) if node_name == node_names[0] else None
        graph.add_edge("__start__", node_name)
        graph.add_edge(node_name, "collect")

    # collect -> debate -> judge -> format_report: debate only starts once
    # every agent has reported in, and only sees what they independently
    # found — it never has a chance to influence the monitoring agents
    # themselves; judge then turns debate's outcome into a real impact call.
    graph.add_edge("collect", "debate")
    graph.add_edge("debate", "judge")
    graph.add_edge("judge", "format_report")
    graph.add_edge("format_report", END)

    return graph.compile()


def run_pipeline() -> PipelineState:
    app = build_graph()
    initial_state = PipelineState(run_date=dt.date.today().isoformat())
    result = app.invoke(initial_state)
    # LangGraph returns a dict-like merged state; rehydrate into our model.
    return PipelineState(**result)

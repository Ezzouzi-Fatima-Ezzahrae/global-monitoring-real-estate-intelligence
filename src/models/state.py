"""PipelineState — the shared, typed state object passed through the
LangGraph orchestrator. Mirrors the InvestigationState pattern from the
fact-checking project: every node reads only what it needs and writes only
the field(s) it owns.
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional

from pydantic import BaseModel, Field

from .debate import DebateLog
from .event import Event
from .impact import ImpactAssessment
from .report import DailyReport


class AgentStep(BaseModel):
    agent: str
    status: str  # "completed" | "failed" | "skipped"
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class PipelineState(BaseModel):
    """Shared, typed LangGraph state. `events` and `trace` are written by
    multiple parallel monitoring-agent nodes in the same graph step, so they
    use an `operator.add` reducer (LangGraph appends each node's partial
    list instead of the default "last write wins", which would otherwise
    raise InvalidUpdateError on concurrent writes — see graph.py)."""

    run_date: str
    events: Annotated[list[Event], operator.add] = Field(default_factory=list)
    debate_log: Optional[DebateLog] = None
    impact_assessments: list[ImpactAssessment] = Field(default_factory=list)
    report: Optional[DailyReport] = None
    errors: list[str] = Field(default_factory=list)
    trace: Annotated[list[AgentStep], operator.add] = Field(default_factory=list)

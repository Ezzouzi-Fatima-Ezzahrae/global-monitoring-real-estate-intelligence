"""DebateLog schema — the structured output of the bounded 3-round debate stage.

See docs: Concept & Architecture Report Section 5; Cahier des Charges FR-05/FR-06.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DebateStatus(str, Enum):
    RESOLVED = "resolved"
    CONTESTED = "contested"
    UNCERTAIN = "uncertain"


class AgentPosition(BaseModel):
    agent: str
    interpretation: str
    argument: str = ""


class ContestedEvent(BaseModel):
    event_id: str
    status: DebateStatus
    positions: list[AgentPosition] = Field(default_factory=list)
    reason: str = Field("", description="Why this is contested/uncertain, or the consensus reached if resolved")


class DebateLog(BaseModel):
    """Guardrail (FR-06): every event that entered the debate must appear in
    exactly one of resolved / contested / uncertain — disagreement is never
    silently dropped.
    """

    round_count: int = Field(..., le=3, description="Debate is bounded to a max of 3 rounds (FR-05)")
    events: list[ContestedEvent] = Field(default_factory=list)

    def status_of(self, event_id: str) -> DebateStatus | None:
        for e in self.events:
            if e.event_id == event_id:
                return e.status
        return None

    model_config = ConfigDict(use_enum_values=True)

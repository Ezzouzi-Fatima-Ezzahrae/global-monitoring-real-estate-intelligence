"""ImpactAssessment schema — the Judge agent's structured output per event.

See docs: Concept & Architecture Report Section 7; Cahier des Charges FR-08/FR-09.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Direction(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class Magnitude(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TimeHorizon(str, Enum):
    IMMEDIATE = "immediate"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"


# Guardrail constant (FR-08): a contested/uncertain event may never be
# reported above this confidence ceiling. Enforced in code, not just prompt.
CONTESTED_CONFIDENCE_CEILING = 0.5


class ImpactAssessment(BaseModel):
    event_id: str
    sector_or_market_affected: str
    direction: Direction
    magnitude: Magnitude
    confidence: float = Field(..., ge=0.0, le=1.0)
    time_horizon: TimeHorizon
    supporting_evidence: list[str] = Field(default_factory=list, description="event_ids and rag_document_ids")
    contested: bool = False
    rationale: str = Field(
        "",
        description=(
            "Plain-language explanation of WHY the Judge reached this direction/magnitude/confidence -- "
            "the reasoning, not just the verdict. Shown directly to Orchid Island in the Digest Console so "
            "a person can see the basis for the assessment, not only its numbers. Defaults to empty string "
            "rather than failing the whole assessment if a model response omits it (see judge_agent.py)."
        ),
    )
    recommended_action: str

    @model_validator(mode="after")
    def enforce_contested_confidence_ceiling(self) -> "ImpactAssessment":
        if self.contested and self.confidence > CONTESTED_CONFIDENCE_CEILING:
            raise ValueError(
                f"Contested event {self.event_id} cannot carry confidence "
                f"{self.confidence} > {CONTESTED_CONFIDENCE_CEILING} (FR-08 guardrail)"
            )
        return self

    model_config = ConfigDict(use_enum_values=True)

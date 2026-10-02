"""Event schema — the structured output every monitoring agent produces.

See docs: Cahier des Charges FR-03, Concept & Architecture Report Section 4.

2026-09-24 addition, at Orchid Island's request ("Source for every event" /
"PDF source traceability" / "Create hooks"): every event must be
independently checkable, not just displayed. SourceType and SourceQuality
below let the console show, for each event, what kind of source it came
from and how much weight that kind of source deserves; PdfReference pins a
document-derived event to the exact page (always validated against the
real page count -- never a guessed number) it came from; OpportunityHook
turns an important event into a business-intelligence framing, built only
from fields that are already real and already hedged (see
src/agents/judge_agent.py's build_hook for exactly how). None of this
replaces source_url/source_name/published_at below, which remain the
actual, always-real proof a person can click through to.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class Relevance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(str, Enum):
    """What kind of source this event came from. Assigned deterministically
    (see src/services/source_classification.py) from the real domain/agent
    that produced the event -- never guessed by an LLM, so it can't drift
    from what the source actually is."""

    OFFICIAL_COMPANY = "official_company"
    GOVERNMENT = "government"
    NEWS = "news"
    BUSINESS_MEDIA = "business_media"
    LINKEDIN = "linkedin"
    PDF = "pdf"
    REPORT = "report"
    OTHER = "other"


class SourceQuality(str, Enum):
    """How much independent weight this source's own claim deserves --
    shown directly in the console (a green/blue/yellow/orange badge) so
    'the company officially announced X' never reads the same as 'a
    newspaper speculates the company may consider X'. NOT_VERIFIED is the
    honest fallback per Orchid Island's own instruction: never invent a
    quality tier when one genuinely can't be determined."""

    PRIMARY = "primary"  # official company / government / official announcement
    CREDIBLE_SECONDARY = "credible_secondary"  # established business/economic media
    SECONDARY = "secondary"  # less direct reporting
    EARLY_UNCONFIRMED = "early_unconfirmed"  # indirect evidence requiring verification
    NOT_VERIFIED = "not_verified"  # no reliable source could be identified


class EventEntities(BaseModel):
    """Extracted entities used later to trigger RAG retrieval."""

    regions: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)


class SupportingSource(BaseModel):
    """An additional real source independently confirming the same event.
    Empty by default on every event -- Phase 1 only adds the field and the
    display for it; automatically detecting which events across different
    agents/documents describe the same real occurrence is cross-document
    entity tracking (a separate, later phase), so this list is populated by
    hand-verified corroboration only for now, never guessed."""

    source_name: Optional[str] = None
    source_url: HttpUrl
    published_at: Optional[date] = None


class PdfReference(BaseModel):
    """Exactly where in an uploaded PDF this event's information was found.
    `page` is set ONLY after being checked against that document's real
    page count (src/agents/document_agent.py) -- never a number the model
    merely claimed. `section` is set ONLY after being checked that it
    actually appears as real text on that same page -- otherwise it is left
    None rather than shown as if it were a confirmed heading."""

    document_id: str
    page: Optional[int] = None
    section: Optional[str] = None


class OpportunityHook(BaseModel):
    """A business-intelligence framing of an important event, built to make
    a potential opportunity for Orchid Island immediately visible without
    the reader having to parse a technical event title.

    Every field here is either copied verbatim from a part of this event or
    its impact assessment that is already real and already hedged
    (why_it_matters, evidence, suggested_action), or built from a small,
    fixed template keyed off real, already-computed values (headline,
    potential_requirements) -- see src/agents/judge_agent.py's build_hook.
    Nothing here is a fresh, ungrounded model claim, and `stage` /
    `confidence_label` are never more confident than the event's own
    underlying confidence number allows."""

    headline: str
    why_it_matters: str
    potential_requirements: list[str] = Field(default_factory=list)
    stage: Literal["early_signal", "confirmed"]
    confidence_label: Literal["low", "medium", "high"]
    evidence: str
    suggested_action: str


class Event(BaseModel):
    """One structured, sourced observation extracted by a monitoring agent.

    Guardrail (FR-02, FR-12): every Event MUST originate from a real,
    retrieved source. `source_url` is required and `retrieval_id` links back
    to the tool-call log so the pipeline can prove, on demand, that this
    event was not fabricated.
    """

    id: str
    agent: str = Field(..., description="Name of the monitoring agent that produced this event")
    headline: str
    summary: str
    entities: EventEntities = Field(default_factory=EventEntities)
    sentiment: Sentiment = Sentiment.NEUTRAL
    relevance_to_real_estate: Relevance = Relevance.LOW
    confidence: float = Field(..., ge=0.0, le=1.0)
    source_url: HttpUrl
    source_name: Optional[str] = None
    published_at: Optional[date] = None
    agent_interpretation: str = ""
    retrieval_id: str = Field(..., description="Links back to the raw tool-call log entry")
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    priority_rank: Optional[int] = Field(
        None,
        description=(
            "2026-09-21 addition, at Orchid Island's request: 1 = highest priority in that day's "
            "report. Assigned once, in src/orchestrator/graph.py's _format_report_node, from the "
            "event's own Judge impact assessment (magnitude, confidence, and how soon it matters), "
            "not by the monitoring agent that produced it -- an Event on its own, before Judge runs, "
            "has no priority yet, hence Optional/None as the honest default rather than a fabricated "
            "rank."
        ),
    )
    source_type: SourceType = Field(
        SourceType.OTHER,
        description="What kind of source this came from -- see src/services/source_classification.py.",
    )
    source_quality: SourceQuality = Field(
        SourceQuality.NOT_VERIFIED,
        description="How much independent weight this source's own claim deserves.",
    )
    pdf_reference: Optional[PdfReference] = Field(
        None, description="Set only for events extracted from an uploaded PDF (src/agents/document_agent.py)."
    )
    supporting_sources: list[SupportingSource] = Field(default_factory=list)
    hook: Optional[OpportunityHook] = Field(
        None, description="Set only for events judged an important business-development signal; see judge_agent.py."
    )

    model_config = ConfigDict(use_enum_values=True)

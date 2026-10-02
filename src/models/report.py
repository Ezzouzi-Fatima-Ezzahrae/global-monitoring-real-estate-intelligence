"""DailyReport schema — the final distributed artifact (FR-11)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .event import Event
from .impact import ImpactAssessment

# 2026-09-21, at Orchid Island's request: a fixed, plain-language
# explanation of how priority_rank is decided, shown directly in the Digest
# Console (and translated there -- see src/api/static/index.html's I18N
# block) rather than left implicit. Not AI-generated text -- a static
# sentence describing the real, deterministic rule in
# src/orchestrator/graph.py's _priority_sort_key, so it can never drift out
# of sync with what the ranking actually does.
PRIORITY_EXPLANATION = (
    "Events are ranked by how big their likely impact on Orchid Island's business is, how "
    "confident that assessment is, and how soon it matters (an immediate development ranks above "
    "a long-term one). A contested assessment (the debate stage did not fully agree on it) still "
    "appears, but ranks lower to reflect that lower confidence. An event Judge has not yet assessed "
    "keeps its place in the list but is ranked after every assessed event."
)


class DailyReport(BaseModel):
    report_date: date
    headline: str
    top_events: list[Event] = Field(default_factory=list)
    priority_explanation: str = Field(default=PRIORITY_EXPLANATION)
    debate_highlights: list[str] = Field(default_factory=list)
    impact_analysis: list[ImpactAssessment] = Field(default_factory=list)
    risks_and_opportunities: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    no_significant_events: bool = Field(
        False, description="FR-15 guardrail: set true instead of manufacturing a finding"
    )

    def to_markdown(self) -> str:
        lines = [f"# Daily Intelligence Report — {self.report_date.isoformat()}", ""]
        lines.append(f"**Headline:** {self.headline}")
        lines.append("")
        if self.no_significant_events:
            lines.append("_No significant events were found today that warrant a notable update._")
            return "\n".join(lines)

        lines.append("## Top Events")
        lines.append(f"_{self.priority_explanation}_")
        lines.append("")
        for e in self.top_events:
            rank_label = f"#{e.priority_rank} " if e.priority_rank else ""
            lines.append(f"- {rank_label}**{e.headline}** ({e.source_name or e.source_url}) — {e.summary}")
        lines.append("")

        lines.append("## Debate Highlights")
        for d in self.debate_highlights:
            lines.append(f"- {d}")
        lines.append("")

        lines.append("## Real Estate Impact Analysis")
        for ia in self.impact_analysis:
            flag = " (CONTESTED)" if ia.contested else ""
            lines.append(
                f"- [{ia.sector_or_market_affected}] {ia.direction}/{ia.magnitude}, "
                f"confidence {ia.confidence:.2f}, horizon {ia.time_horizon}{flag} — {ia.recommended_action}"
            )
        lines.append("")

        lines.append("## Risks & Opportunities")
        for r in self.risks_and_opportunities:
            lines.append(f"- {r}")
        lines.append("")

        lines.append("## Recommended Actions")
        for a in self.recommended_actions:
            lines.append(f"- {a}")
        lines.append("")

        lines.append("## Confidence & Limitations")
        for l in self.limitations:
            lines.append(f"- {l}")
        lines.append("")

        lines.append("## Sources")
        for c in self.citations:
            lines.append(f"- {c}")

        return "\n".join(lines)

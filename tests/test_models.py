import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.impact import ImpactAssessment


def test_impact_assessment_rejects_high_confidence_on_contested_event():
    """The FR-08 guardrail must be enforced in code, not just in a prompt:
    a contested event can never be reported with high confidence."""
    with pytest.raises(ValidationError):
        ImpactAssessment(
            event_id="e1",
            sector_or_market_affected="Marrakech hospitality RE",
            direction="negative",
            magnitude="medium",
            confidence=0.9,
            time_horizon="short_term",
            contested=True,
            recommended_action="monitor",
        )


def test_impact_assessment_allows_low_confidence_on_contested_event():
    ia = ImpactAssessment(
        event_id="e1",
        sector_or_market_affected="Marrakech hospitality RE",
        direction="negative",
        magnitude="medium",
        confidence=0.4,
        time_horizon="short_term",
        contested=True,
        recommended_action="monitor",
    )
    assert ia.confidence == 0.4

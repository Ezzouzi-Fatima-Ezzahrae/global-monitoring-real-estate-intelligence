"""Deterministic numeric comparison tool (FR-10 / Cahier des Charges).

Pure Python, no LLM involved — used by the Judge to aggregate/compare
sentiment scores or figures across events rather than letting the model
estimate a trend.
"""
from __future__ import annotations

import statistics
from typing import Sequence

from pydantic import BaseModel


class ComparisonResult(BaseModel):
    observed_count: int
    observed_min: float
    observed_max: float
    observed_avg: float


def compare_values(observed: Sequence[float]) -> ComparisonResult:
    if not observed:
        return ComparisonResult(observed_count=0, observed_min=0.0, observed_max=0.0, observed_avg=0.0)
    return ComparisonResult(
        observed_count=len(observed),
        observed_min=min(observed),
        observed_max=max(observed),
        observed_avg=statistics.fmean(observed),
    )

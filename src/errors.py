"""Shared exception types.

MissingConfigurationError is how this system "asks" for what it needs: when
a required credential isn't set, code raises this immediately with a clear,
actionable message instead of silently substituting fake data. There is no
mock/fallback mode anywhere in this codebase — every deliverable this system
produces must be built entirely from real API calls to real sources. If
something required is missing, the correct behavior is to stop loudly and
say exactly what's needed, not to produce output that looks real but isn't.
"""
from __future__ import annotations


class MissingConfigurationError(RuntimeError):
    """Raised when a required credential/setting is not configured. The
    message should always say exactly which .env variable to set."""

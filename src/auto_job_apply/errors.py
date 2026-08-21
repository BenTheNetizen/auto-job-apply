"""Shared error taxonomy for auto_job_apply.

Every error carries a machine-usable ``.context`` dict so callers can stash
partial state (e.g. a partially extracted form) alongside the failure.
"""

from __future__ import annotations

from typing import Any


class AutoJobApplyError(Exception):
    """Base error for auto_job_apply."""

    def __init__(self, message: str = "", *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, Any] = dict(context) if context else {}


class ConfigError(AutoJobApplyError):
    """Configuration is missing or invalid."""


class UnsupportedATSError(AutoJobApplyError):
    """The job URL does not match any supported ATS plugin."""

    def __init__(self, url: str, *, context: dict[str, Any] | None = None) -> None:
        self.url = url
        super().__init__(
            f"Unsupported ATS for URL: {url}",
            context={"url": url, **(context or {})},
        )


class ExtractionError(AutoJobApplyError):
    """Field extraction from an application form failed.

    Callers should stash any partially extracted form in
    ``context["partial"]``.
    """


class PlannerError(AutoJobApplyError):
    """Answer planning failed."""


class SubmissionError(AutoJobApplyError):
    """Application submission failed."""

    def __init__(
        self,
        fields_missing: list[str] | None = None,
        message: str | None = None,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.fields_missing: list[str] = list(fields_missing) if fields_missing else []
        msg = message or f"Submission failed; missing required fields: {self.fields_missing}"
        super().__init__(
            msg,
            context={"fields_missing": self.fields_missing, **(context or {})},
        )


class EmailPollError(AutoJobApplyError):
    """Email polling/parsing pipeline failed."""


__all__ = [
    "AutoJobApplyError",
    "ConfigError",
    "UnsupportedATSError",
    "ExtractionError",
    "PlannerError",
    "SubmissionError",
    "EmailPollError",
]

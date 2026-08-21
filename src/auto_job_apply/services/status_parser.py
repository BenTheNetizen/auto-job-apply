"""Classify recruiter email into an application status.

Strategy: deterministic rules first (regex/wordlist, ordered by priority);
when no rule matches (or confidence < 0.8), fall back to a structured LLM
call via ``services.llm``. The module performs no file I/O; the LLM fallback
is the only side effect and is lazily imported so tests without API keys
can import and exercise the rule path freely.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel

SNIPPET_MAX_CHARS = 600
RULE_CONFIDENCE = 0.9
LLM_CONFIDENCE = 0.7
LLM_CONFIDENCE_THRESHOLD = 0.8


class ApplicationStatus(str, Enum):
    acknowledged = "acknowledged"
    rejected = "rejected"
    interview_scheduled = "interview_scheduled"
    assessment = "assessment"
    offer = "offer"
    withdrawn = "withdrawn"
    unknown = "unknown"


class ParsedStatus(BaseModel):
    status: ApplicationStatus
    confidence: float
    raw_snippet: str


class _LlmStatus(BaseModel):
    """Structured output schema for the LLM fallback."""

    status: ApplicationStatus
    snippet: str


# (status, patterns). First match wins, so list most decisive first:
# rejection language beats the polite "thank you for applying" preamble that
# rejection emails usually open with.
_RULES: list[tuple[ApplicationStatus, tuple[str, ...]]] = [
    (
        ApplicationStatus.rejected,
        (
            r"\bunfortunately\b",
            r"\bnot (?:be )?moving forward\b",
            r"\bwill not be (?:moving forward|proceeding)\b",
            r"\bdecided to (?:move forward|proceed|go) with other",
            r"\bother candidates?\b",
            r"\bposition has been filled\b",
            r"\bno longer (?:under consideration|considering)\b",
            r"\bregret to inform\b",
        ),
    ),
    (
        ApplicationStatus.offer,
        (
            r"\boffer letter\b",
            r"\bformal offer\b",
            # Require the noun "offer": "pleased to extend an invitation to
            # interview" must not classify as an offer.
            r"\bpleased to (?:extend|offer) (?:you )?(?:a |an |the )?(?:formal )?offer\b",
            r"\bdelighted to offer\b",
            r"\boffer of employment\b",
        ),
    ),
    (
        ApplicationStatus.interview_scheduled,
        (
            r"\binterview (?:invitation|invite|scheduled)\b",
            r"\binvite you to (?:an? )?(?:interview|call)\b",
            r"\bschedule (?:a|an|your) (?:call|interview|phone screen)\b",
            r"\bwe'?d (?:like|love) to (?:invite|interview|schedule)\b",
            r"\bphone screen\b",
            r"\binterview with\b",
        ),
    ),
    (
        ApplicationStatus.assessment,
        (
            r"\btake[- ]home\b",
            r"\b(?:coding|technical|skills?) (?:challenge|assessment|test|assignment)\b",
            r"\bonline assessment\b",
            r"\bhackerrank|codesignal|karat\b",
        ),
    ),
    (
        ApplicationStatus.withdrawn,
        (
            r"\bapplication (?:has been |was )?(?:cancell?ed|withdrawn)\b",
            r"\bwithdraw(?:n|al|ing)? (?:your )?application\b",
            r"\bjob posting has been closed\b",
        ),
    ),
    (
        ApplicationStatus.acknowledged,
        (
            r"\bthank(?:s| you) for (?:applying|your application|your interest)\b",
            r"\bapplication (?:has been |was )?received\b",
            r"\bwe (?:have )?received your application\b",
            r"\bconfirm(?:ing)? (?:receipt of )?your application\b",
            r"\bapplication (?:was|has been) submitted\b",
        ),
    ),
]

_COMPILED: list[tuple[ApplicationStatus, list[re.Pattern[str]]]] = [
    (status, [re.compile(p, re.IGNORECASE) for p in patterns])
    for status, patterns in _RULES
]


def _snippet_around(text: str, start: int, end: int) -> str:
    """Window around the match, capped at SNIPPET_MAX_CHARS."""
    half = (SNIPPET_MAX_CHARS - (end - start)) // 2
    lo = max(0, start - max(half, 0))
    hi = min(len(text), end + max(half, 0))
    return text[lo:hi].strip()[:SNIPPET_MAX_CHARS]


def _rule_match(subject: str, body: str) -> ParsedStatus | None:
    for status, patterns in _COMPILED:
        for pattern in patterns:
            m = pattern.search(body)
            text = body
            if m is None:
                m = pattern.search(subject)
                text = subject
            if m is not None:
                return ParsedStatus(
                    status=status,
                    confidence=RULE_CONFIDENCE,
                    raw_snippet=_snippet_around(text, m.start(), m.end()),
                )
    return None


def _llm_classify(subject: str, body: str) -> ParsedStatus:
    """LLM fallback. Never raises: failures degrade to unknown/0.0."""
    try:
        from auto_job_apply.services import llm as llm_mod

        model = llm_mod.get_llm(role="parser")
        runnable = llm_mod.structured(model, _LlmStatus)
        payload = (
            "Classify this recruiter email about a job application into one "
            "status. Return the enum value and a brief verbatim snippet "
            "(<=600 chars) from the email that justifies it.\n\n"
            f"SUBJECT: {subject}\n\nBODY:\n{body[:4000]}"
        )
        result: Any = runnable.invoke(payload)
        llm_mod.log_usage(getattr(result, "raw", result))
        snippet = (result.snippet or body[:SNIPPET_MAX_CHARS])[:SNIPPET_MAX_CHARS]
        return ParsedStatus(
            status=result.status,
            confidence=LLM_CONFIDENCE,
            raw_snippet=snippet,
        )
    except Exception:  # noqa: BLE001 - parser must never take the poll loop down
        return ParsedStatus(
            status=ApplicationStatus.unknown,
            confidence=0.0,
            raw_snippet=body[:SNIPPET_MAX_CHARS],
        )


def parse(subject: str, body: str) -> ParsedStatus:
    """Classify an email. Rules first; LLM fallback on miss/low confidence."""
    subject = subject or ""
    body = body or ""
    rule_hit = _rule_match(subject, body)
    if rule_hit is not None and rule_hit.confidence >= LLM_CONFIDENCE_THRESHOLD:
        return rule_hit
    if rule_hit is not None:
        return rule_hit  # confident enough; no rule currently scores below 0.8
    return _llm_classify(subject, body)


__all__ = [
    "ApplicationStatus",
    "ParsedStatus",
    "parse",
    "RULE_CONFIDENCE",
    "LLM_CONFIDENCE",
    "LLM_CONFIDENCE_THRESHOLD",
    "SNIPPET_MAX_CHARS",
]

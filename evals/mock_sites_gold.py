"""Pydantic models for mock-sites gold labels and submission payloads.

The eval runner loads gold labels from evals/mock-sites/gold/<case>.json into
GoldCase, and submission payloads recorded by the dev server at
evals/mock-sites/submissions/<case>.json into SubmissionPayload.

Gold cases also drive the dev server's submit-recorder behavior via the
optional behavioral keys on GoldCase:

- ``confirmation_style``: "toast" (inline banner) or "redirect" (navigate to
  /<ats>/<case>/confirmation). Default "toast".
- ``reject_rules``: server-side validation; a field value not matching
  ``pattern`` yields HTTP 422 with ``error``.
- ``bot_block``: /submit always answers HTTP 403 (bot-detection block page).
- ``progressive_field``: a field that only exists after a first rejected
  submission (HTTP 422 naming it); a second POST including it succeeds.

Cases with ``bot_block`` or ``progressive_field`` are "behavioral" — they need
dedicated harnesses (confirmation-detection / human-loop-eval leaves) and are
excluded from the standard eval-gate corpus returned by ``all_cases()``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

MOCK_SITES_DIR = Path(__file__).parent / "mock-sites"
GOLD_DIR = MOCK_SITES_DIR / "gold"
SUBMISSIONS_DIR = MOCK_SITES_DIR / "submissions"

FieldType = Literal[
    "text",
    "textarea",
    "select",
    "radio",
    "checkbox-group",
    "date",
    "file",
]

# Sentinel in gold labels: the answer is LLM-generated; scorer checks
# non-emptiness and content rules rather than exact match.
GENERATED = "@generated@"

ConfirmationStyle = Literal["toast", "redirect"]


class GoldField(BaseModel):
    key: str
    label: str
    type: FieldType
    required: bool
    expected: str | list[str]


class RejectRule(BaseModel):
    """Server-side validation rule: /submit returns 422 with ``error`` when
    the submitted value for ``field`` does not fully match ``pattern``."""

    field: str
    pattern: str
    error: str


class ProgressiveField(BaseModel):
    """Field revealed only after a first rejected submission. ``expected`` is
    what the human-loop harness supplies on re-submission; it intentionally
    does NOT come from the applicant profile fixture."""

    key: str
    label: str
    type: FieldType
    required: bool
    options: list[str] | None = None
    expected: str | list[str] | None = None


class GoldCase(BaseModel):
    case: str  # e.g. "ashby/basic"
    title: str
    fields: list[GoldField]
    confirmation_style: ConfirmationStyle = "toast"
    reject_rules: list[RejectRule] = []
    bot_block: bool = False
    progressive_field: ProgressiveField | None = None

    @property
    def required_fields(self) -> list[GoldField]:
        return [f for f in self.fields if f.required]

    @property
    def behavioral(self) -> bool:
        """True when the case requires a dedicated harness and cannot join
        the standard fill→submit→score eval gate."""
        return self.bot_block or self.progressive_field is not None


class SubmissionPayload(BaseModel):
    applicationId: str  # e.g. "ashby/basic"
    fields: dict[str, Any]


def gold_path(case: str) -> Path:
    return GOLD_DIR / f"{case.replace('/', '__')}.json"


def submission_path(case: str) -> Path:
    return SUBMISSIONS_DIR / f"{case.replace('/', '__')}.json"


def load_gold(case: str) -> GoldCase:
    return GoldCase.model_validate(json.loads(gold_path(case).read_text()))


def load_submission(case: str) -> SubmissionPayload:
    return SubmissionPayload.model_validate(
        json.loads(submission_path(case).read_text())
    )


def all_cases(include_behavioral: bool = False) -> list[str]:
    """Standard eval-gate cases by default.

    Behavioral cases (bot_block / progressive_field) are excluded unless
    ``include_behavioral`` is set, so the standard fill→submit→score runner
    (evals/run_evals.py) never picks up cases that cannot submit successfully
    on a first pass.
    """
    cases: list[str] = []
    for p in sorted(GOLD_DIR.glob("*.json")):
        case = p.stem.replace("__", "/")
        if not include_behavioral:
            raw = json.loads(p.read_text())
            if raw.get("bot_block") or raw.get("progressive_field"):
                continue
        cases.append(case)
    return cases


def behavioral_cases() -> list[str]:
    """Cases excluded from the standard gate (bot_block / progressive_field)."""
    standard = set(all_cases())
    return [c for c in all_cases(include_behavioral=True) if c not in standard]

"""Pydantic models for mock-sites gold labels and submission payloads.

The eval runner loads gold labels from evals/mock-sites/gold/<case>.json into
GoldCase, and submission payloads recorded by the dev server at
evals/mock-sites/submissions/<case>.json into SubmissionPayload.
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


class GoldField(BaseModel):
    key: str
    label: str
    type: FieldType
    required: bool
    expected: str | list[str]


class GoldCase(BaseModel):
    case: str  # e.g. "ashby/basic"
    title: str
    fields: list[GoldField]

    @property
    def required_fields(self) -> list[GoldField]:
        return [f for f in self.fields if f.required]


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


def all_cases() -> list[str]:
    return sorted(p.stem.replace("__", "/") for p in GOLD_DIR.glob("*.json"))

"""Applicant profile: authoritative key-value store backed by
applicant_profile.csv under DATA.dir.

Seeded with the built-in question keys on first touch; only rows with
source ``manual`` or ``learned`` are authoritative.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from auto_job_apply.config import data_dir
from auto_job_apply.utils.csv_store import CsvStore

PROFILE_FILENAME = "applicant_profile.csv"

SEED_KEYS: tuple[str, ...] = (
    "full_name",
    "email",
    "resume_path",
    "phone",
    "linkedin_url",
    "github_url",
    "website",
)

AUTHORITATIVE_SOURCES: tuple[str, ...] = ("manual", "learned")


class ApplicantProfileRow(BaseModel):
    question_key: str
    answer: str = ""
    source: Literal["manual", "learned", "llm_draft"] = "llm_draft"
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


def _store(path: str | Path | None = None) -> CsvStore[ApplicantProfileRow]:
    file_path = Path(path) if path else data_dir() / PROFILE_FILENAME
    return CsvStore(file_path, ApplicantProfileRow, key_field="question_key")


def _seed(store: CsvStore[ApplicantProfileRow]) -> None:
    for key in SEED_KEYS:
        if store.get(key) is None:
            store.append(
                ApplicantProfileRow(
                    question_key=key, answer="", source="manual"
                )
            )


def get(key: str, path: str | Path | None = None) -> str | None:
    store = _store(path)
    _seed(store)
    row = store.get(key)
    return row.answer if row else None


def set(
    key: str, answer: str, source: str, path: str | Path | None = None
) -> None:
    store = _store(path)
    _seed(store)
    store.upsert(
        "question_key",
        ApplicantProfileRow(
            question_key=key,
            answer=answer,
            source=source,  # type: ignore[arg-type]
        ),
    )


def get_authoritative(key: str, path: str | Path | None = None) -> str | None:
    store = _store(path)
    _seed(store)
    row = store.get(key)
    if not row:
        return None
    if row.source not in AUTHORITATIVE_SOURCES:
        return None
    return row.answer if row.answer else None


def all(path: str | Path | None = None) -> list[ApplicantProfileRow]:
    store = _store(path)
    _seed(store)
    return store.read_all()


__all__ = ["ApplicantProfileRow", "SEED_KEYS", "get", "set", "get_authoritative", "all"]

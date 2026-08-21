"""Shared ``applications.csv`` row model.

This module is the single home for the applications row schema so the
fill pipeline and the email monitor write the same file shape.

NOTE: filler-submitter (application-filling leaf) imports this module and
may tighten ``fields_json`` from ``list[dict]`` to ``list[Field]`` when its
Field model lands. Keep changes backwards compatible (additive only).

Per master spec: one row per job application; ``fields_json`` and
``status_history_json`` are JSON-in-column structured fields.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from auto_job_apply.config import data_dir
from auto_job_apply.utils.csv_store import CsvStore

APPLICATIONS_CSV = "applications.csv"


class StatusEvent(BaseModel):
    """One status change on an application (from filler, email, or user)."""

    status: str
    source: str  # "filler" | "email" | "user"
    raw_snippet: str = ""
    at: datetime


class ApplicationsRow(BaseModel):
    """One job application row in applications.csv."""

    id: str
    job_url: str
    ats_type: str = ""  # "ashby" | "greenhouse" | "lever" (filler normalizes)
    # NOTE: two status namespaces share this column by design today:
    # fill-pipeline states (needs_review/ready_to_submit/submitted/failed)
    # and email-derived states (acknowledged/rejected/...). Email events
    # overwrite it per the agentmail-poll leaf spec; history is preserved
    # in status_history_json.
    status: str = ""
    job_title: str = ""  # optional; enables subject-substring email matching
    fields_json: list[dict[str, Any]] = Field(default_factory=list)
    status_history_json: list[StatusEvent] = Field(default_factory=list)
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    screenshot_dir: str = ""


def applications_store(path: str | Path | None = None) -> CsvStore[ApplicationsRow]:
    """CsvStore for applications.csv (default: under DATA.dir)."""
    resolved = Path(path) if path is not None else data_dir() / APPLICATIONS_CSV
    return CsvStore(resolved, ApplicationsRow, key_field="id")


def append_status(
    app_id: str, event: StatusEvent, *, path: str | Path | None = None
) -> bool:
    """Append ``event`` to an application's history and set its top-level status.

    Read-modify-write under the store's file lock. Returns False when no
    application with ``app_id`` exists (caller decides what unmatched means).
    """
    store = applications_store(path)
    row = store.get(app_id)
    if row is None:
        return False
    history = [*row.status_history_json, event]
    return store.update(
        app_id,
        row.model_copy(
            update={"status": event.status, "status_history_json": history}
        ),
    )


__all__ = [
    "APPLICATIONS_CSV",
    "ApplicationsRow",
    "StatusEvent",
    "applications_store",
    "append_status",
]

"""Review surface over applications.csv — the shared seam for the API and CLI.

Implements the operations from the review-api-cli leaf: list/inspect rows,
edit fields (with the self-learning write-back), confirm (needs_review →
ready_to_submit with the never-fabricate gate), and submit via the filler.

Both the FastAPI routes (server.py) and the CLI (cli.py) go through these
functions; the CLI prefers the HTTP API when the server is reachable and
falls back to calling this module directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from auto_job_apply.errors import SubmissionError
from auto_job_apply.logging import logger
from auto_job_apply.services import learning
from auto_job_apply.services.applications import (
    ApplicationsRow,
    StatusEvent,
    applications_store,
)
from datetime import UTC, datetime


def list_applications(
    status: str | None = None, *, path: str | Path | None = None
) -> list[ApplicationsRow]:
    """All applications, optionally filtered by top-level status."""
    rows = applications_store(path).read_all()
    if status:
        rows = [r for r in rows if r.status == status]
    return rows


def get_application(app_id: str, *, path: str | Path | None = None) -> ApplicationsRow:
    """One application row (404-style KeyError when missing)."""
    row = applications_store(path).get(app_id)
    if row is None:
        raise KeyError(f"Unknown application id: {app_id}")
    return row


def edit_field(
    app_id: str,
    field_key: str,
    value: str,
    *,
    path: str | Path | None = None,
) -> ApplicationsRow:
    """Edit one field's answer; learns non-empty answers from the edit.

    The edit is written back to ``fields_json`` (matching on the field's
    stable key); the edited value flows into the submit payload because
    ``filler.submit`` reads answers from ``fields_json``. When the value is
    non-empty the (label, value) pair is learned as ``source="learned"`` so
    future forms auto-answer it.
    """
    store = applications_store(path)
    row = store.get(app_id)
    if row is None:
        raise KeyError(f"Unknown application id: {app_id}")

    label: str | None = None
    found = False
    new_fields: list[dict[str, Any]] = []
    for f in row.fields_json:
        if isinstance(f, dict) and f.get("key") == field_key:
            f = dict(f, answer=value)
            label = str(f.get("label") or field_key)
            found = True
        new_fields.append(f)
    if not found:
        raise KeyError(f"Unknown field_key {field_key!r} on application {app_id}")

    updated = row.model_copy(update={"fields_json": new_fields})
    store.update(app_id, updated)

    if value:
        learning.learn(label or field_key, value, source="learned")
        logger.info("review: learned %r from edit on %s", label or field_key, app_id)
    return updated


def confirm_application(
    app_id: str,
    *,
    learn_from_edits: bool = False,
    path: str | Path | None = None,
) -> ApplicationsRow:
    """Confirm a ``needs_review`` application → ``ready_to_submit``.

    The gate is absolute: any required field still blank blocks confirmation
    (we never fabricate required answers). ``learn_from_edits`` re-learns
    every non-empty reviewer answer as ``source="learned"`` — opt-in because
    ``edit_field`` already learns on each edit.
    """
    store = applications_store(path)
    row = store.get(app_id)
    if row is None:
        raise KeyError(f"Unknown application id: {app_id}")
    if row.status != "needs_review":
        raise SubmissionError(
            message=f"Cannot confirm application in status {row.status!r} "
            "(only 'needs_review' rows can be confirmed)",
            context={"application_id": app_id, "status": row.status},
        )

    missing = [
        str(f.get("label") or f.get("key"))
        for f in row.fields_json
        if isinstance(f, dict) and f.get("required") and not (f.get("answer") or "").strip()
    ]
    if missing:
        raise SubmissionError(
            fields_missing=missing,
            message=f"{len(missing)} required field(s) still blank",
            context={"application_id": app_id, "missing": missing},
        )

    if learn_from_edits:
        for f in row.fields_json:
            if isinstance(f, dict) and (f.get("answer") or "").strip():
                learning.learn(str(f.get("label") or f.get("key")), f["answer"], source="learned")

    from auto_job_apply.services.applications import append_status

    append_status(
        app_id,
        StatusEvent(status="ready_to_submit", source="user", at=datetime.now(UTC)),
        path=path,
        update_top_level=True,
    )
    logger.info("review: confirmed %s -> ready_to_submit", app_id)
    return store.get(app_id) or row


def submit_application(app_id: str, *, path: str | Path | None = None) -> ApplicationsRow:
    """Trigger the guarded filler submit for a confirmed application."""
    from auto_job_apply.services import filler

    return filler.submit(app_id, applications_path=path)


__all__ = [
    "list_applications",
    "get_application",
    "edit_field",
    "confirm_application",
    "submit_application",
]

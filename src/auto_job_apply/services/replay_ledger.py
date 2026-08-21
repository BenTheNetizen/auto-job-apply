"""Replay-safe ledger of processed inbound messages.

Guarantee: a message id is never applied twice. ``record`` is called only
AFTER the status update has landed in applications.csv, so a crash between
the two replays the *poll* (message still unread) but ``is_processed``
short-circuits the duplicate. ``record`` itself is an idempotent upsert, so
even a crash after the applications.csv write but before/inside record is
safe to retry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from auto_job_apply.config import data_dir
from auto_job_apply.utils.csv_store import CsvStore

PROCESSED_MESSAGES_CSV = "processed_messages.csv"


class ProcessedMessage(BaseModel):
    message_id: str
    processed_at: datetime
    application_id: str | None = None
    status: str | None = None


def ledger_store(path: str | Path | None = None) -> CsvStore[ProcessedMessage]:
    """CsvStore for processed_messages.csv (default: under DATA.dir)."""
    resolved = Path(path) if path is not None else data_dir() / PROCESSED_MESSAGES_CSV
    return CsvStore(resolved, ProcessedMessage, key_field="message_id")


def is_processed(message_id: str, path: str | Path | None = None) -> bool:
    """True when this message id has already been recorded."""
    return ledger_store(path).get(message_id) is not None


def record(
    message_id: str,
    application_id: str | None = None,
    status: str | None = None,
    path: str | Path | None = None,
) -> ProcessedMessage:
    """Record a message as processed. Idempotent (upsert by message_id)."""
    row = ProcessedMessage(
        message_id=message_id,
        processed_at=datetime.now(timezone.utc),
        application_id=application_id,
        status=status,
    )
    ledger_store(path).upsert("message_id", row)
    return row


__all__ = [
    "PROCESSED_MESSAGES_CSV",
    "ProcessedMessage",
    "ledger_store",
    "is_processed",
    "record",
]

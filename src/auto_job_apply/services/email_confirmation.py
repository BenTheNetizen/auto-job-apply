"""Wait for the employer's confirmation email after a successful submit.

Bounded, never-raises loop over the AgentMail inbox: polls unread mail until
a message matching the application is classified as an acknowledgement (or
stronger), or until the configurable deadline passes. The outcome is a
first-class enum; both interesting outcomes are recorded as status-history
events on the application row (top-level status is never clobbered — a
``submitted`` row stays ``submitted``).

Config (config/settings.json → EMAIL):
- ``confirmation_wait_enabled`` (default true) — off switch.
- ``confirmation_timeout_seconds`` (default 600) — outer deadline.
- ``confirmation_poll_seconds`` (default 30) — interval between inbox scans.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from auto_job_apply.config import settings
from auto_job_apply.logging import logger
from auto_job_apply.services import email_monitor, replay_ledger
from auto_job_apply.services.applications import StatusEvent, append_status
from auto_job_apply.services.status_parser import ApplicationStatus, parse


class EmailConfirmationStatus(str, Enum):
    """Outcome of waiting for the employer confirmation email."""

    RECEIVED = "received"  # confirmation-classified email arrived in time
    TIMEOUT = "timeout"  # no confirmation email within the window
    NOT_CHECKED = "not_checked"  # waiting disabled by config


# "acknowledged (or stronger)" statuses treated as a confirmation.
CONFIRMING_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.acknowledged,
        ApplicationStatus.interview_scheduled,
        ApplicationStatus.assessment,
        ApplicationStatus.offer,
    }
)

EVENT_RECEIVED = "confirmation_received"
EVENT_TIMEOUT = "confirmation_timeout"


def _wait_enabled() -> bool:
    """Module-level seam (tests monkeypatch this without touching settings)."""
    return bool(settings.get("EMAIL.confirmation_wait_enabled", True))


def _record(application_id: str, event_status: str, raw_snippet: str, apps_path: str | Path | None) -> None:
    """Append a confirmation outcome to history; top-level status is left alone."""
    ok = append_status(
        application_id,
        StatusEvent(
            status=event_status,
            source="email",
            raw_snippet=raw_snippet,
            at=datetime.now(timezone.utc),
        ),
        path=apps_path,
        update_top_level=False,
    )
    if not ok:
        logger.warning(
            "email_confirmation: application %r not found; %r event skipped",
            application_id,
            event_status,
        )


def _scan_once(
    client: Any,
    inbox_id: str,
    application_id: str,
    apps_path: str | Path | None,
    ledger_path: str | Path | None,
) -> bool:
    """One inbox scan; consume the matching confirmation if found.

    Only a message that both matches the application AND classifies as an
    acknowledgement-or-stronger is consumed (marked read, ledger-recorded).
    Everything else is left unread for the regular email-monitor cycle.
    """
    for raw in email_monitor._list_unread(client, inbox_id):
        msg = email_monitor.normalize_sdk_message(raw)
        try:
            row = email_monitor.match_application(msg, apps_path)
        except Exception:  # noqa: BLE001 — a bad match must not kill the wait
            logger.warning(
                "email_confirmation: match failed for message %s", msg.message_id
            )
            continue
        if row is None or row.id != application_id:
            continue
        parsed = parse(msg.subject, msg.text)
        if parsed.status not in CONFIRMING_STATUSES:
            continue  # e.g. a rejection for this app — not a confirmation
        _record(application_id, EVENT_RECEIVED, parsed.raw_snippet, apps_path)
        replay_ledger.record(
            msg.message_id, row.id, parsed.status.value, ledger_path
        )
        email_monitor._mark_read(client, inbox_id, msg.message_id)
        logger.info(
            "email_confirmation: %s consumed message %s (%s)",
            application_id,
            msg.message_id,
            parsed.status.value,
        )
        return True
    return False


def _wait(
    application_id: str,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    client: Any | None,
    account: str | None,
    apps_path: str | Path | None,
    ledger_path: str | Path | None,
    sleep: Callable[[float], None],
) -> EmailConfirmationStatus:
    if client is None:
        client = email_monitor._get_client()
    account = account or str(settings.get("EMAIL.account", ""))
    inbox_id = email_monitor._resolve_inbox_id(client, account)
    deadline = time.monotonic() + timeout_seconds
    while True:
        if _scan_once(client, inbox_id, application_id, apps_path, ledger_path):
            return EmailConfirmationStatus.RECEIVED
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _record(application_id, EVENT_TIMEOUT, "", apps_path)
            return EmailConfirmationStatus.TIMEOUT
        sleep(min(poll_interval_seconds, remaining))


def wait_for_confirmation(
    application_id: str,
    *,
    timeout_seconds: float | None = None,
    poll_interval_seconds: float | None = None,
    client: Any | None = None,
    account: str | None = None,
    apps_path: str | Path | None = None,
    ledger_path: str | Path | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> EmailConfirmationStatus:
    """Poll the AgentMail inbox for the application's confirmation email.

    Bounded and never raises: disabled config -> NOT_CHECKED (no I/O);
    infrastructure failure -> TIMEOUT with a warning (no history event — the
    wait never actually ran); deadline reached -> TIMEOUT with a
    ``confirmation_timeout`` history event; matching ack -> RECEIVED with a
    ``confirmation_received`` history event and the message consumed (mark
    read + ledger, so the regular poll cycle never reprocesses it).
    """
    if not _wait_enabled():
        logger.info("email_confirmation: wait disabled by config -> NOT_CHECKED")
        return EmailConfirmationStatus.NOT_CHECKED
    if not os.environ.get("AGENTMAIL_API_KEY") and client is None:
        logger.warning(
            "email_confirmation: AGENTMAIL_API_KEY is not set -> TIMEOUT (no poll run)"
        )
        return EmailConfirmationStatus.TIMEOUT
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else float(settings.get("EMAIL.confirmation_timeout_seconds", 600))
    )
    poll = (
        poll_interval_seconds
        if poll_interval_seconds is not None
        else float(settings.get("EMAIL.confirmation_poll_seconds", 30))
    )
    try:
        outcome = _wait(
            application_id,
            timeout_seconds=timeout,
            poll_interval_seconds=poll,
            client=client,
            account=account,
            apps_path=apps_path,
            ledger_path=ledger_path,
            sleep=sleep,
        )
        logger.info(
            "email_confirmation: %s -> %s", application_id, outcome.value
        )
        return outcome
    except Exception:  # noqa: BLE001 — spec: never raises
        logger.warning(
            "email_confirmation: wait raised for %s", application_id, exc_info=True
        )
        return EmailConfirmationStatus.TIMEOUT


__all__ = [
    "EmailConfirmationStatus",
    "CONFIRMING_STATUSES",
    "wait_for_confirmation",
    "EVENT_RECEIVED",
    "EVENT_TIMEOUT",
]

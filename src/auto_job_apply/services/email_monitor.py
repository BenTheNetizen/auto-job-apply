"""AgentMail polling loop: match -> parse -> update -> ledger -> mark-read.

The per-message handler ``handle_message`` is deliberately shaped like a
webhook handler (one normalized message in, one outcome out) so a future
webhook transport swaps in without touching matching/parsing/updating.

CLI seam: this module exposes ``poll_once`` and ``run_forever``; the
``python -m auto_job_apply.cli email-monitor [--once] [--interval N]``
subcommand is wired up by the review-api-cli leaf.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from auto_job_apply.config import settings
from auto_job_apply.errors import EmailPollError
from auto_job_apply.services import replay_ledger
from auto_job_apply.services.applications import (
    ApplicationsRow,
    StatusEvent,
    append_status,
    applications_store,
)
from auto_job_apply.services.status_parser import ApplicationStatus, parse

logger = logging.getLogger("auto_job_apply.email_monitor")

UNREAD_LABEL = "unread"
APP_ID_HEADER = "x-application-id"
_APP_ID_SUBJECT_RE = re.compile(r"\[app:([A-Za-z0-9-]+)\]")


# ---------------------------------------------------------------------------
# Normalized message shape (decoupled from the AgentMail SDK model so tests
# and a future webhook transport can construct it directly).
# ---------------------------------------------------------------------------


@dataclass
class IncomingMessage:
    message_id: str
    subject: str = ""
    text: str = ""
    from_address: str = ""
    thread_id: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def normalize_sdk_message(m: Any) -> IncomingMessage:
    """Convert an AgentMail SDK Message into IncomingMessage."""
    from_raw = getattr(m, "from_", None) or ""
    headers = getattr(m, "headers", None) or {}
    return IncomingMessage(
        message_id=str(getattr(m, "message_id")),
        subject=str(getattr(m, "subject", "") or ""),
        text=str(getattr(m, "text", None) or getattr(m, "extracted_text", None) or ""),
        from_address=str(from_raw),
        thread_id=str(getattr(m, "thread_id", "") or ""),
        headers={str(k).lower(): str(v) for k, v in dict(headers).items()},
    )


class HandleResult(BaseModel):
    message_id: str
    outcome: Literal["updated", "duplicate", "unmatched", "error"]
    application_id: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


class PollSummary(BaseModel):
    polled: int = 0
    updated: int = 0
    duplicates: int = 0
    unmatched: int = 0
    errors: int = 0
    results: list[HandleResult] = []


# ---------------------------------------------------------------------------
# Matching: message -> application row
# ---------------------------------------------------------------------------


def _org_slug(job_url: str) -> str:
    """Org slug from a hosted ATS URL: jobs.ashbyhq.com/<org>/..., etc."""
    path = urlparse(job_url).path.strip("/")
    return path.split("/")[0].lower() if path else ""


def _sender_domain(from_address: str) -> str:
    addr = from_address.strip().lower()
    if "<" in addr and ">" in addr:  # "Name <a@b.c>"
        addr = addr[addr.index("<") + 1 : addr.index(">")]
    return addr.rsplit("@", 1)[-1] if "@" in addr else ""


def match_application(
    msg: IncomingMessage, apps_path: str | Path | None = None
) -> ApplicationsRow | None:
    """Match a message to an application row.

    Priority: explicit application id (header/subject token) -> org match
    (sender domain or subject vs job_url org slug) -> job title substring.
    Returns None when nothing matches (caller leaves the message unread).
    """
    store = applications_store(apps_path)

    # 1. Explicit application id.
    explicit = msg.headers.get(APP_ID_HEADER)
    if not explicit:
        m = _APP_ID_SUBJECT_RE.search(msg.subject)
        explicit = m.group(1) if m else None
    if explicit:
        row = store.get(explicit)
        if row is not None:
            return row
        logger.warning("explicit application id %r not found", explicit)

    # 2. Org match via sender domain or subject.
    domain = _sender_domain(msg.from_address)
    subject_l = msg.subject.lower()
    for row in store.read_all():
        org = _org_slug(row.job_url)
        if not org:
            continue
        domain_hit = bool(domain) and (
            org in domain or domain.split(".")[0] in org
        )
        subject_hit = org in subject_l
        if domain_hit or subject_hit:
            return row

    # 3. Job-title substring in subject.
    for row in store.read_all():
        title = (row.job_title or "").strip().lower()
        if title and title in subject_l:
            return row

    return None


# ---------------------------------------------------------------------------
# Handling / polling
# ---------------------------------------------------------------------------


def handle_message(
    msg: IncomingMessage,
    *,
    client: Any,
    inbox_id: str,
    ledger_path: str | Path | None = None,
    apps_path: str | Path | None = None,
) -> HandleResult:
    """Process one inbound message (webhook-shaped).

    Order: match -> parse -> append status -> ledger.record -> mark read.
    Ledger is written only after the applications.csv update lands, and
    duplicates short-circuit before any update.
    """
    if replay_ledger.is_processed(msg.message_id, ledger_path):
        # Crash between record and mark-read leaves the message unread;
        # mark it read now without re-applying the update.
        _mark_read(client, inbox_id, msg.message_id)
        return HandleResult(message_id=msg.message_id, outcome="duplicate")

    app = match_application(msg, apps_path)
    if app is None:
        logger.warning(
            "unmatched message %s (from=%s subject=%r); leaving unread",
            msg.message_id,
            msg.from_address,
            msg.subject,
        )
        return HandleResult(message_id=msg.message_id, outcome="unmatched")

    parsed = parse(msg.subject, msg.text)
    if parsed.status is ApplicationStatus.unknown and parsed.confidence == 0.0:
        raise EmailPollError(
            f"status classification failed for message {msg.message_id}",
            context={"message_id": msg.message_id, "application_id": app.id},
        )

    event = StatusEvent(
        status=parsed.status.value,
        source="email",
        raw_snippet=parsed.raw_snippet,
        at=datetime.now(timezone.utc),
    )
    update_top_level = (
        parsed.status is not ApplicationStatus.unknown
        # Email classifications must never wedge a pre-submit pipeline state:
        # the review gate keys on the row's top-level status, so an email
        # (e.g. an early auto-ack) landing on needs_review/ready_to_submit /
        # in_progress goes to history only.
        and app.status not in {"needs_review", "ready_to_submit", "in_progress"}
    )
    if not update_top_level:
        # Ambiguous LLM classification or a pre-submit pipeline row: record
        # the event in history but never clobber the row's top-level status.
        logger.warning(
            "message %s classified=%s (confidence=%.2f) for app in status %r; "
            "appending history only, leaving top-level status unchanged",
            msg.message_id,
            parsed.status.value,
            parsed.confidence,
            app.status,
        )
    if not append_status(
        app.id, event, path=apps_path, update_top_level=update_top_level
    ):
        raise EmailPollError(
            f"matched application {app.id} vanished before status update",
            context={"message_id": msg.message_id, "application_id": app.id},
        )

    replay_ledger.record(
        msg.message_id, app.id, parsed.status.value, ledger_path
    )
    _mark_read(client, inbox_id, msg.message_id)
    return HandleResult(
        message_id=msg.message_id,
        outcome="updated",
        application_id=app.id,
        status=parsed.status.value,
    )


def _mark_read(client: Any, inbox_id: str, message_id: str) -> None:
    client.inboxes.messages.update(
        inbox_id, message_id, remove_labels=[UNREAD_LABEL]
    )


def _get_client() -> Any:
    """Construct the AgentMail client lazily (needs AGENTMAIL_API_KEY)."""
    api_key = os.environ.get("AGENTMAIL_API_KEY")
    if not api_key:
        raise EmailPollError(
            "AGENTMAIL_API_KEY is not set",
            context={"env_key": "AGENTMAIL_API_KEY"},
        )
    from agentmail import AgentMail

    return AgentMail(api_key=api_key)


def _resolve_inbox_id(client: Any, account: str) -> str:
    for inbox in client.inboxes.list().inboxes:
        if getattr(inbox, "email", None) == account or getattr(inbox, "inbox_id", None) == account:
            return str(inbox.inbox_id)
    raise EmailPollError(
        f"no AgentMail inbox found for account {account}",
        context={"account": account},
    )


def _list_unread(client: Any, inbox_id: str) -> list[Any]:
    messages: list[Any] = []
    page_token = None
    while True:
        resp = client.inboxes.messages.list(
            inbox_id, labels=[UNREAD_LABEL], page_token=page_token
        )
        messages.extend(getattr(resp, "messages", []) or [])
        page_token = getattr(resp, "next_page_token", None)
        if not page_token:
            return messages


def poll_once(
    *,
    client: Any | None = None,
    account: str | None = None,
    ledger_path: str | Path | None = None,
    apps_path: str | Path | None = None,
) -> PollSummary:
    """One poll cycle: fetch unread, handle each, never die on one bad message."""
    if client is None:
        client = _get_client()
    account = account or str(settings.get("EMAIL.account", ""))
    inbox_id = _resolve_inbox_id(client, account)

    summary = PollSummary()
    for raw in _list_unread(client, inbox_id):
        summary.polled += 1
        msg = normalize_sdk_message(raw)
        try:
            result = handle_message(
                msg,
                client=client,
                inbox_id=inbox_id,
                ledger_path=ledger_path,
                apps_path=apps_path,
            )
        except Exception as exc:  # noqa: BLE001 - one bad message must not kill the loop
            logger.exception("failed to handle message %s", msg.message_id)
            result = HandleResult(
                message_id=msg.message_id, outcome="error", error=str(exc)
            )
        summary.results.append(result)
        if result.outcome == "updated":
            summary.updated += 1
        elif result.outcome == "duplicate":
            summary.duplicates += 1
        elif result.outcome == "unmatched":
            summary.unmatched += 1
        else:
            summary.errors += 1
    return summary


def run_forever(
    interval_seconds: int | None = None,
    *,
    client: Any | None = None,
    account: str | None = None,
) -> None:
    """Poll on a schedule until interrupted. ``interval_seconds`` overrides
    EMAIL.poll_interval_seconds (the CLI ``--interval`` flag maps here)."""
    interval = int(
        interval_seconds
        if interval_seconds is not None
        else settings.get("EMAIL.poll_interval_seconds", 300)
    )
    logger.info("email-monitor polling every %ss", interval)
    while True:
        try:
            summary = poll_once(client=client, account=account)
            logger.info(
                "poll complete: polled=%s updated=%s dupes=%s unmatched=%s errors=%s",
                summary.polled,
                summary.updated,
                summary.duplicates,
                summary.unmatched,
                summary.errors,
            )
        except EmailPollError:
            raise
        except Exception:  # noqa: BLE001 - transient SDK/network failure
            logger.exception("poll cycle failed; retrying in %ss", interval)
        time.sleep(interval)


__all__ = [
    "IncomingMessage",
    "HandleResult",
    "PollSummary",
    "normalize_sdk_message",
    "match_application",
    "handle_message",
    "poll_once",
    "run_forever",
    "UNREAD_LABEL",
    "APP_ID_HEADER",
]

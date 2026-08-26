"""Filler & submitter: deterministic Playwright fill of an ATS form,
artifact capture, review gating, and the review-triggered submit action.

Pipeline position: extractor -> planner -> **filler** -> review-api-cli.

``fill(url, plan, application_id)`` re-walks the live form (shared DOM-walk
from the extractor), applies the planner's answers field-by-field, captures
screenshots/HTML artifacts, and persists an ``applications.csv`` row. The
review gate is absolute: ``plan.review_required`` yields
``status="needs_review"`` and the form is *filled* but never submitted;
otherwise the row lands as ``ready_to_submit``.

``submit(application_id)`` is only called by the review surface after a
human (or the verifying agent) has confirmed the row. It re-walks the form
privately, injects the persisted answers from ``fields_json`` (which carry
any reviewer edits), clicks the plugin's submit control, and records the
outcome. On Playwright timeout/error it escalates once to a Browserbase
session when ``BROWSERBASE_API_KEY`` is configured.

Testability: the real browser is only touched inside ``_open_page`` /
``_open_page_browserbase``; tests inject fake pages through the
``page_opener``/``browserbase_opener`` seams, so no browser is needed in
unit tests. The DOM surface used by the filler is deliberately narrow
(``get_by_label``/``get_by_role`` returning locators with
``fill``/``check``/``uncheck``/``select_option``/``set_input_files`` and a
``count()``), which keeps fakes simple.
"""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from auto_job_apply.config import settings
from auto_job_apply.errors import SubmissionError
from auto_job_apply.graphs.planner import AnswerPlan
from auto_job_apply.logging import logger
from auto_job_apply.services import profile
from auto_job_apply.services.applications import (
    ApplicationsRow,
    StatusEvent,
    append_status,
    applications_store,
)
from auto_job_apply.services.ats_registry import ATSPlugin, plugin_for
from auto_job_apply.services.email_confirmation import wait_for_confirmation
from auto_job_apply.services.extractor import (
    MULTI_VALUE_SEP,
    ApplicationForm,
    Field,
    discover_fields,
)
from auto_job_apply.utils import artifacts

PageOpener = Callable[[str, bool, int], Any]

_CONFIRM_TEXT = (
    "thank you",
    "application received",
    "application submitted",
    "successfully submitted",
    "we'll be in touch",
    "we will be in touch",
)


# --- browser seams (real browser only here; tests inject fakes) -----------


def _filler_timeout_ms() -> int:
    return int(settings.get("FILLER.timeout_ms", 45_000))


def _filler_headless() -> bool:
    return bool(settings.get("FILLER.headless", True))


@contextmanager
def _open_page(url: str, headless: bool, timeout_ms: int) -> Iterator[Any]:
    """Open ``url`` in a local Chromium page."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(url, timeout=timeout_ms)
            yield page
        finally:
            browser.close()


@contextmanager
def _open_page_browserbase(url: str, headless: bool, timeout_ms: int) -> Iterator[Any]:
    """Open ``url`` through a Browserbase session (bot-detection escalation).

    Lazy-imported so the dependency is only required on the escalation path.
    """
    from browserbase import Browserbase  # type: ignore[import-not-found]
    from playwright.sync_api import sync_playwright

    bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
    session = bb.sessions.create(project_id=os.environ.get("BROWSERBASE_PROJECT_ID"))
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(session.connect_url)
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(url, timeout=timeout_ms)
            yield page
        finally:
            browser.close()


# --- field application ----------------------------------------------------


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _labeled(page: Any, label: str) -> Any:
    """Locator for a label-associated control (duck-typed for fakes)."""
    return page.get_by_label(label)


def _fill_field(page: Any, field: Field, value: str, resume_path: str | None) -> bool:
    """Apply one answer to one field. Returns True when applied.

    Unknown fields are skipped with a warning (flagged, never fabricated).
    A locator that matches nothing (``count() == 0``) is reported unfilled so
    the caller can record the gap instead of crashing the whole fill.
    """
    if field.type in ("text", "textarea", "date"):
        control = _labeled(page, field.label)
        if control.count() == 0:
            logger.warning("filler: no control for label %r", field.label)
            return False
        control.first.fill(value)
        return True
    if field.type == "select":
        control = _labeled(page, field.label)
        if control.count() == 0:
            logger.warning("filler: no select for label %r", field.label)
            return False
        # Greenhouse select2 keeps the real <select> in the DOM, so a direct
        # select_option on the labeled control is the deterministic path.
        control.first.select_option(label=value)
        return True
    if field.type == "radio":
        # Scope to the field's own group first (fieldset with matching legend)
        # so same-value options across different groups don't collide.
        group = page.get_by_role("group", name=re.compile(re.escape(field.label.replace("*", "").strip()), re.IGNORECASE))
        if group.count() > 0:
            option = group.first.get_by_role("radio", name=value)
        else:
            option = page.get_by_role("radio", name=value)
        if option.count() == 0:
            logger.warning("filler: no radio option %r for %r", value, field.label)
            return False
        option.first.check()
        return True
    if field.type == "checkbox":
        control = _labeled(page, field.label)
        if control.count() == 0:
            logger.warning("filler: no checkbox for label %r", field.label)
            return False
        if _truthy(value):
            control.first.check()
        else:
            control.first.uncheck()
        return True
    if field.type == "checkbox-group":
        applied = False
        # Canonical separator is MULTI_VALUE_SEP ("|"); tolerate "," and ";"
        # for values written before the convention was enforced.
        wanted = {
            v.strip().lower()
            for v in re.split(r"[|,;]", value)
            if v.strip()
        }
        for option in field.options or []:
            if option.strip().lower() in wanted:
                page.get_by_role("checkbox", name=option).first.check()
                applied = True
        if not applied:
            logger.warning("filler: no checkbox-group options matched for %r", field.label)
        return applied
    if field.type == "file":
        control = _labeled(page, field.label)
        if control.count() == 0:
            # file inputs often have no label association; fall back to the
            # plugin-visible file selector.
            control = page.locator('input[type="file"]')
        if control.count() == 0:
            logger.warning("filler: no file input for label %r", field.label)
            return False
        target = value or resume_path
        if not target:
            logger.warning("filler: no resume path available for %r", field.label)
            return False
        control.first.set_input_files(target)
        return True
    logger.warning("filler: skipping unknown field type %r (%r)", field.type, field.label)
    return False


def _answers_by_key(plan: AnswerPlan) -> dict[str, str]:
    return {a.field_key: a.value for a in plan.answers if a.value}


def _event(status: str, source: str = "filler", snippet: str = "") -> StatusEvent:
    return StatusEvent(
        status=status, source=source, raw_snippet=snippet, at=datetime.now(UTC)
    )


# --- public API -----------------------------------------------------------


def fill(
    url: str,
    plan: AnswerPlan,
    application_id: str,
    *,
    page_opener: PageOpener | None = None,
    applications_path: str | Path | None = None,
) -> ApplicationForm:
    """Fill the form at ``url`` with ``plan`` answers and persist the row.

    Never submits. Returns the form with ``answer`` set on answered fields.
    The persisted row is ``needs_review`` when the plan requires review,
    otherwise ``ready_to_submit``; all ``fields_json[*].submitted`` stay
    False until :func:`submit`.
    """
    plugin = plugin_for(url)
    opener = page_opener or _open_page
    timeout_ms = _filler_timeout_ms()
    answers = _answers_by_key(plan)
    resume_path = profile.get_authoritative("resume_path")

    with opener(url, _filler_headless(), timeout_ms) as page:
        plugin.pre_extract(page)
        fields = discover_fields(page, plugin)
        unfilled: list[str] = []
        for field in fields:
            try:
                value = answers.get(field.key)
                if value is None:
                    # File fields default to the profile resume path; the
                    # planner has nothing useful to say about uploads.
                    if field.type == "file" and resume_path:
                        if _fill_field(page, field, "", resume_path):
                            field.answer = resume_path
                    continue
                if _fill_field(page, field, value, resume_path):
                    field.answer = value
                else:
                    unfilled.append(field.key)
            except Exception as exc:  # noqa: BLE001 — one bad control never aborts the fill
                logger.warning(
                    "filler: failed to fill %r (%s): %s", field.label, field.type, exc
                )
                unfilled.append(field.key)
        plugin.post_fill(page, answers)
        try:
            artifacts.snapshot_page(application_id, page, "fill")
        except Exception as exc:  # noqa: BLE001 — artifacts must never abort a fill
            logger.warning("filler: fill snapshot failed for %s: %s", application_id, exc)

    status = "needs_review" if (plan.review_required or unfilled_required(fields, plan, unfilled)) else "ready_to_submit"
    row = ApplicationsRow(
        id=application_id,
        job_url=url,
        ats_type=plugin.name,
        status=status,
        fields_json=[f.model_dump() for f in fields],
        status_history_json=[_event(status)],
        created_at=datetime.now(UTC),
        screenshot_dir=str(artifacts.artifact_dir(application_id)),
    )
    applications_store(applications_path).upsert("id", row)
    if unfilled:
        logger.warning("filler: %d field(s) could not be filled: %s", len(unfilled), unfilled)
    logger.info("filler: filled %s -> status=%s", application_id, status)
    return ApplicationForm(
        url=url, ats_type=plugin.name, fields=fields, discovered_iterations=1
    )


def unfilled_required(fields: list[Field], plan: AnswerPlan, unfilled: list[str]) -> bool:
    """True when any required field still lacks an applied answer."""
    missing = {f.key for f in plan.missing_required}
    return any(f.required and (f.key in missing or f.key in unfilled) for f in fields)


def submit(
    application_id: str,
    *,
    page_opener: PageOpener | None = None,
    browserbase_opener: PageOpener | None = None,
    applications_path: str | Path | None = None,
    wait_for_email: bool = False,
    email_timeout_seconds: float | None = None,
) -> ApplicationsRow:
    """Submit a reviewed application. Only called from the review surface.

    Guards: the row must exist and be ``ready_to_submit`` (never submit a
    ``needs_review`` row — the review gate is absolute). On success the row
    becomes ``submitted`` with ``submitted_at`` set and every filled field
    marked ``submitted=True``; on failure it becomes ``failed`` and a
    :class:`SubmissionError` is raised.

    Escalation: a Playwright-level failure on the local browser triggers one
    retry through Browserbase when ``BROWSERBASE_API_KEY`` is present. When
    ``wait_for_email`` is set, a successful submit is followed by a bounded
    inbox poll for the employer's confirmation email (opt-in for sync
    callers; outcome is logged, never affects the submitted row).
    """
    store = applications_store(applications_path)
    row = store.get(application_id)
    if row is None:
        raise SubmissionError(message=f"Unknown application id: {application_id}")
    if row.status != "ready_to_submit":
        raise SubmissionError(
            message=f"Refusing to submit application in status {row.status!r} "
            "(must be 'ready_to_submit'; needs_review requires human confirmation)",
            context={"application_id": application_id, "status": row.status},
        )

    plugin = plugin_for(row.job_url)
    answers = {
        f.get("key"): f.get("answer")
        for f in row.fields_json
        if isinstance(f, dict) and f.get("key") and f.get("answer")
    }
    resume_path = profile.get_authoritative("resume_path")

    openers: list[tuple[str, PageOpener]] = [("local", page_opener or _open_page)]
    if os.environ.get("BROWSERBASE_API_KEY"):
        openers.append(("browserbase", browserbase_opener or _open_page_browserbase))

    last_error: Exception | None = None
    for mode, opener in openers:
        try:
            _submit_once(plugin, row, answers, resume_path, opener, application_id)
        except Exception as exc:  # noqa: BLE001 — escalate, then record
            last_error = exc
            logger.warning("filler: submit via %s failed for %s: %s", mode, application_id, exc)
            continue
        # success path
        updated = _finalize_success(store, row)
        logger.info("filler: submitted %s via %s", application_id, mode)
        if wait_for_email:
            _wait_for_email_confirmation(
                updated.id, applications_path, email_timeout_seconds
            )
        return updated

    _finalize_failure(store, row, last_error)
    raise SubmissionError(
        message=f"Submission failed for {application_id}: {last_error}",
        context={"application_id": application_id, "cause": str(last_error)},
    )


def _submit_once(
    plugin: ATSPlugin,
    row: ApplicationsRow,
    answers: dict[str, str | None],
    resume_path: str | None,
    opener: PageOpener,
    application_id: str,
) -> None:
    """Fill privately from persisted answers and click the submit control."""
    timeout_ms = _filler_timeout_ms()
    with opener(row.job_url, _filler_headless(), timeout_ms) as page:
        plugin.pre_extract(page)
        fields = discover_fields(page, plugin)
        for field in fields:
            value = answers.get(field.key)
            if value is None:
                if field.type == "file" and resume_path:
                    _fill_field(page, field, "", resume_path)
                continue
            _fill_field(page, field, value, resume_path)
        plugin.post_fill(page, answers)
        artifacts.snapshot_page(application_id, page, "submit-pre")
        plugin.submit_button(page).first.click()
        # Post-click failures are non-retryable: the click already hit the
        # employer's server, so escalating to Browserbase would double-submit.
        # Confirmation artifacts are best-effort evidence only.
        try:
            _await_confirmation(page)
        except Exception as exc:  # noqa: BLE001 — click already landed; warn, never retry
            logger.warning(
                "filler: post-click confirmation check failed for %s (submission may already be on the employer server): %s",
                application_id,
                exc,
            )
        try:
            artifacts.snapshot_page(application_id, page, "submit-post")
        except Exception as exc:  # noqa: BLE001 — post-click artifact failure must not escalate
            logger.warning(
                "filler: submit-post snapshot failed for %s: %s", application_id, exc
            )


def _wait_for_email_confirmation(
    application_id: str,
    applications_path: str | Path | None,
    timeout_seconds: float | None,
) -> None:
    """Post-submit inbox poll; an opt-in step that must never affect the row."""
    try:
        outcome = wait_for_confirmation(
            application_id,
            timeout_seconds=timeout_seconds,
            apps_path=applications_path,
        )
        logger.info("filler: email confirmation %s -> %s", application_id, outcome.value)
    except Exception:  # noqa: BLE001 — waiting must never affect submit success
        logger.warning(
            "filler: email confirmation wait raised for %s",
            application_id,
            exc_info=True,
        )


def _await_confirmation(page: Any) -> None:
    """Best-effort post-submit confirmation: settle, then look for success text.

    Lenient by design — mock sites record the POST without navigating. A
    detected error banner raises :class:`SubmissionError`, but the caller
    treats every post-click failure as non-retryable (the click already hit
    the employer's server), so this only surfaces as a warning upstream.
    """
    try:
        page.wait_for_load_state("networkidle")
    except Exception:  # noqa: BLE001 — mock pages / long polls may never idle
        pass
    try:
        content = page.content().lower()
    except Exception:  # noqa: BLE001
        return
    for marker in ("error submitting", "submission failed", "something went wrong"):
        if marker in content:
            raise SubmissionError(message=f"Post-submit error banner detected: {marker}")
    if any(marker in content for marker in _CONFIRM_TEXT):
        logger.info("filler: submit confirmation text detected")


def _finalize_success(store: Any, row: ApplicationsRow) -> ApplicationsRow:
    """Mark the row submitted; best-effort event append (already persisted)."""
    append_status(row.id, _event("submitted"), path=store.path)
    current = store.get(row.id) or row
    fields = [dict(f, submitted=bool(f.get("answer"))) if isinstance(f, dict) else f
              for f in current.fields_json]
    updated = current.model_copy(
        update={
            "status": "submitted",
            "submitted_at": datetime.now(UTC),
            "fields_json": fields,
        }
    )
    store.update(row.id, updated)
    return updated


def _finalize_failure(store: Any, row: ApplicationsRow, error: Exception | None) -> None:
    """Mark the row failed with the error snippet in history."""
    append_status(
        row.id,
        _event("failed", snippet=str(error)[:600]),
        path=store.path,
        update_top_level=True,
    )


__all__ = ["fill", "submit"]

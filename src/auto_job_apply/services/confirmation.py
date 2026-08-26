"""Submission confirmation detection.

Machine-checkable post-submit signal shared by the ATS plugins and the
filler's submit path. Replaces the filler's old generic ``_CONFIRM_TEXT``
page scan with a composed check per plugin: redirect-style URL change →
toast-style success banner → validation-rejection markers → bot-detection
signals → else ``UNKNOWN``.

The helpers are duck-typed on the page (``page.url``, ``page.content()``,
``page.locator(selector).count()``), so unit fakes are trivial. The browser
is only touched inside this module's tiny poll loop (~5s max).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Iterable

from auto_job_apply.logging import logger


class SubmissionConfirmation(str, Enum):
    """Outcome of a post-submit confirmation check."""

    CONFIRMED = "confirmed"  # definitive success signal
    REJECTED_VALIDATION = "rejected_validation"  # server rejected bad/missing fields
    REJECTED_BOT = "rejected_bot"  # bot-detection / captcha / generic block
    UNKNOWN = "unknown"  # no signal either way (never blocks a real submit)


# Generic fallbacks (used in addition to each plugin's ATS-specific selectors).
GENERIC_SUCCESS_TEXT = (
    "thank you",
    "application received",
    "application submitted",
    "successfully submitted",
    "we'll be in touch",
    "we will be in touch",
)
GENERIC_VALIDATION_MARKERS = (
    "error submitting",
    "submission failed",
    "something went wrong",
    "please correct",
    "fix the errors",
    "invalid ",
)
BOT_MARKERS = (
    "verify you are human",
    "captcha",
    "cloudflare",
    "access denied",
)
BOT_SELECTORS = (
    'iframe[src*="captcha"]',
    'iframe[src*="challenge"]',
)

MAX_WAIT_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 0.25


def _wait_settle(page: Any) -> None:
    """Best-effort networkidle settle (mock pages may never fire networkidle)."""
    try:
        page.wait_for_load_state("networkidle")
    except Exception:  # noqa: BLE001
        pass


def _page_text(page: Any) -> str:
    try:
        return page.content().lower()
    except Exception:  # noqa: BLE001
        return ""


def _selector_visible(page: Any, selector: str) -> bool:
    locator = page.locator(selector)
    try:
        return locator.count() > 0
    except Exception:  # noqa: BLE001 — fakes raise on odd selectors; treat absent
        return False


def check_redirect(page: Any, patterns: Iterable[str]) -> bool:
    """True when the page URL contains any confirmation/thanks pattern."""
    url = (getattr(page, "url", "") or "").lower()
    return any(pattern in url for pattern in patterns)


def check_toast(page: Any, selectors: Iterable[str]) -> bool:
    """ATS-specific success selector visible, or generic success text on page."""
    if any(_selector_visible(page, selector) for selector in selectors):
        return True
    content = _page_text(page)
    return any(marker in content for marker in GENERIC_SUCCESS_TEXT)


def check_validation(page: Any, selectors: Iterable[str]) -> bool:
    """ATS-specific error-summary selector, or generic error text on page."""
    if any(_selector_visible(page, selector) for selector in selectors):
        return True
    content = _page_text(page)
    return any(marker in content for marker in GENERIC_VALIDATION_MARKERS)


def check_bot(page: Any) -> bool:
    """Captcha iframe / verify-human / Cloudflare / access-denied heuristics."""
    if any(_selector_visible(page, selector) for selector in BOT_SELECTORS):
        return True
    content = _page_text(page)
    return any(marker in content for marker in BOT_MARKERS)


def confirm_by(
    page: Any,
    *,
    redirect_patterns: Iterable[str],
    toast_selectors: Iterable[str] = (),
    validation_selectors: Iterable[str] = (),
    wait: bool = True,
) -> SubmissionConfirmation:
    """Compose the standard signal order (per the confirmation-detection leaf):
    redirect → toast → validation → bot → UNKNOWN. Polls for up to
    ``MAX_WAIT_SECONDS`` because toasts render asynchronously after the click.
    """
    if wait:
        _wait_settle(page)
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while True:
        if check_redirect(page, redirect_patterns):
            return SubmissionConfirmation.CONFIRMED
        if check_toast(page, toast_selectors):
            return SubmissionConfirmation.CONFIRMED
        if check_validation(page, validation_selectors):
            return SubmissionConfirmation.REJECTED_VALIDATION
        if check_bot(page):
            return SubmissionConfirmation.REJECTED_BOT
        if time.monotonic() >= deadline:
            logger.info(
                "confirmation: no definitive signal after %.1fs -> UNKNOWN",
                MAX_WAIT_SECONDS,
            )
            return SubmissionConfirmation.UNKNOWN
        time.sleep(POLL_INTERVAL_SECONDS)


__all__ = [
    "SubmissionConfirmation",
    "GENERIC_SUCCESS_TEXT",
    "GENERIC_VALIDATION_MARKERS",
    "BOT_MARKERS",
    "BOT_SELECTORS",
    "confirm_by",
    "check_redirect",
    "check_toast",
    "check_validation",
    "check_bot",
]

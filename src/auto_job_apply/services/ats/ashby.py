"""Ashby-specific ATS plugin (selectors + quirks only).

Extraction/planning/submission logic lives in the shared leaves; this module
tells the extractor where Ashby fields live and the submitter what to click.

Quirk notes:
- Ashby serves its application form as a plain ``<form>`` root; fields are
  associated through ``<label>`` elements (``label:has-text(...)`` matching).
- Required fields are marked by a trailing ``*`` in the label text and/or the
  HTML ``required`` attribute on the control. Treat either marker as required.
- A cookie banner with an "Accept" button often overlays the form head; the
  extractor's ``pre_extract`` dismissal keeps it out of the way.
- Selector style deliberately favors role/text matching over brittle ids.
- ``submit_button`` matches "Submit Application" or plain "Submit".

Playwright is imported lazily (``TYPE_CHECKING`` only) so the plugin module
stays importable before the extractor/filler leaves add the dependency.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from auto_job_apply.services.ats_registry import (
    ATS_HOST_PATTERNS,
    hostname_matches,
    register,
)

if TYPE_CHECKING:
    from playwright.sync_api import Locator

SUBMIT_TEXT = re.compile(r"Submit Application|Submit")


class AshbyPlugin:
    """Plugin singleton registered under name ``"ashby"``."""

    name = "ashby"

    _SELECTORS = {
        "form_root": "form",
        "label": "label",
        "checkbox_or_radio": "input[type=checkbox], input[type=radio]",
        "select": "select",
        "file": "input[type=file]",
        "required_attr": "[required]",
    }

    def __init__(self) -> None:
        self._selectors = dict(self._SELECTORS)

    def detect(self, url: str) -> bool:
        """``True`` when the URL host is an Ashby host (or subdomain)."""
        return hostname_matches(url, ATS_HOST_PATTERNS[self.name])

    def base_selectors(self) -> dict[str, str]:
        """Selector map; returned as a copy so callers cannot mutate state."""
        return dict(self._selectors)

    def pre_extract(self, page: Any) -> None:
        """Dismiss Ashby's cookie banner (``button:has-text("Accept")``)."""
        accept = page.locator('button:has-text("Accept")')
        if accept.count() and accept.first.is_visible():
            accept.first.click()

    def submit_button(self, page: Any) -> Locator:
        """The submit control; matches "Submit Application" or "Submit"."""
        return page.get_by_role("button", name=SUBMIT_TEXT).or_(
            page.locator("button[type=submit]").filter(has_text=SUBMIT_TEXT)
        )

    def post_fill(self, page: Any, answers: Any) -> None:
        """No Ashby-specific post-fill behavior for v0."""


plugin = register(AshbyPlugin())

__all__ = ["AshbyPlugin", "plugin"]

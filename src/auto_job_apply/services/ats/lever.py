"""Lever ATS plugin.

Selectors and quirks for ``jobs.lever.co`` application forms. Plugins own
selector/quirk knowledge only; extraction, planning, and submission live in
shared leaves (see ``.spec/AutoJobApply/application-filling/index.md``).

Quirk notes (lever-specific):

- The application form sits under ``div.application-form`` (with a generic
  ``form`` fallback for older postings).
- Required fields are marked by a ``*`` adjacent to the label text, not by
  HTML ``required`` attributes — the extractor's label-driven logic reads the
  marker off the label, which is why ``required_marker`` is a hint string
  here rather than a CSS selector.
- Questions may be grouped into accordion sections behind ``.toggle``
  headers. Fields inside a collapsed section do not exist in the DOM until
  the header is clicked, so :meth:`LeverPlugin.pre_extract` clicks every
  visible ``.toggle`` header once before the extractor walks. Some postings
  reveal further nested questions reactively as earlier fields are filled;
  that dynamic-reveal walk belongs to the extractor's iterative discovery
  loop, not to this plugin.
"""

from __future__ import annotations

from typing import Any

from auto_job_apply.services.ats_registry import (
    ATS_HOST_PATTERNS,
    hostname_matches,
    register,
)


class LeverPlugin:
    """Lever-specific selectors + quirks (``jobs.lever.co``)."""

    name = "lever"

    def detect(self, url: str) -> bool:
        return hostname_matches(url, ATS_HOST_PATTERNS["lever"])

    def base_selectors(self) -> dict[str, str]:
        """Selector map consumed by the shared extractor/filler.

        Keys are stable names so fallback selector behaviour stays readable;
        strings prefer role/label/text over brittle ids per the leaf spec.
        """
        return {
            # Form root; ``div.application-form form`` preferred, generic
            # ``form`` tolerated for older postings.
            "form": "div.application-form form, form",
            # Accordion section headers revealed by ``pre_extract``.
            "accordion_toggle": ".toggle",
            # Label element strategy (lever labels wrap their inputs, so use
            # the label text node, not a ``for`` attribute).
            "label": "label",
            # Required marker appears as a literal ``*`` adjacent to the
            # label text; the extractor tests label text, not the attribute.
            "required_marker": "*",
            # Field groups inside accordion bodies.
            "section_body": ".accordion-body",
        }

    def pre_extract(self, page: Any) -> None:
        """Expand accordion ``.toggle`` headers so fields exist in the DOM.

        Clicks each visible ``.toggle`` header once. Individual click failures
        are tolerated (stale/detached header mid-dom-update) and never abort
        the walk. Absence of toggles is a no-op.
        """
        toggles = page.locator(self.base_selectors()["accordion_toggle"])
        count = toggles.count()
        for i in range(count):
            try:
                toggles.nth(i).click()
            except Exception:
                continue

    def submit_button(self, page: Any) -> Any:
        """The submit control: ``button``/``input[type=submit]`` with text
        ``Submit`` (value or adjacent text).
        """
        return page.locator(
            "button[type=submit]:has-text('Submit'), "
            "input[type=submit][value*='Submit' i]"
        )

    def post_fill(self, page: Any, answers: Any) -> None:
        """Lever needs no post-fill hook; the filler handles file uploads and
        final state. Explicit no-op so the protocol is satisfied and the hook
        seam is documented.
        """
        return None



PLUGIN = register(LeverPlugin())

__all__ = ["LeverPlugin", "PLUGIN"]

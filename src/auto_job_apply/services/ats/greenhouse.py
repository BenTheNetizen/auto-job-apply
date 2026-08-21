"""Greenhouse (boards.greenhouse.io) plugin: selectors and page quirks.

Satisfies the ``ATSPlugin`` protocol defined in
``auto_job_apply.services.ats_registry``. Registration into the registry is
done best-effort at import time: when the registry module is available we
register, otherwise we skip silently. The registry leaf lands separately in
the M2 wave; once it is on main this self-registration is what routes
greenhouse URLs to this plugin.

Selectors intentionally prefer labels/roles/structure over brittle ids, so
they work on both the real Greenhouse DOM and the eval mock at
``evals/mock-sites/src/GreenhousePage.jsx``.

Greenhouse quirks handled here:
- Required markers: ``span.asterisk`` inside the label, or a native
  ``[required]`` attribute on the control.
- Voluntary demographics (veterans/disability/gender) live in a collapsed
  section; ``pre_extract`` clicks the ``.expand_all`` toggle.
- Cookie / consent modals: ``pre_extract`` dismisses common patterns
  (``Accept`` buttons) if present.
- Selects: Greenhouse often renders selects through select2, which hides the
  real ``<select>`` and renders a div-based dropdown. The data-source select
  stays in the DOM (class ``select2-hidden-accessible``) — the extractor
  routes ``type=select`` handling to the hidden select directly and uses
  the clickable widget only as a fallback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:  # Playwright is introduced by the extractor leaf.
    from playwright.sync_api import Locator, Page  # pragma: no cover


SUBMIT_TEXT = "Submit"


class GreenhousePlugin:
    """Greenhouse ATS plugin singleton (registered at import below)."""

    name = "greenhouse"

    def detect(self, url: str) -> bool:
        # Proper host check: handles subdomains like boards.greenhouse.io
        # but not fakes like boards.greenhouse.io.evil.com or path substrings.
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        return host == "boards.greenhouse.io"

    def base_selectors(self) -> dict[str, str]:
        return {
            "form": "#application form",
            "field": "label",
            "required_label_marker": "span.asterisk",
            "required_attr_marker": "[required]",
            "demographic_section": "fieldset, .demographic-section",
            "select": "select",
            "select2_widget": ".select2-container",
        }

    def pre_extract(self, page: "Page") -> None:
        """Dismiss cookie/consent modals and expand accordion sections.

        Both steps are tolerant: absence of modal/accordion is fine.
        Duck-typed page (either a real Playwright Page or a fake in tests)
        must support ``query_selector`` returning a clickable element or None.
        """
        for text in ("Accept", "I Agree", "Agree"):
            modal_button = _query(page, f'button:has-text("{text}")')
            if modal_button is not None:
                modal_button.click()
                return
        expand_toggle = _query(page, ".expand_all")
        if expand_toggle is not None:
            expand_toggle.click()

    def submit_button(self, page: "Page") -> "Locator":
        """Primary/submit locator: input[type=submit] or a ``Submit`` button.

        Duck-typed: any object answering ``page.locator(selector)`` (or a
        recorded selector in fakes) will do.
        """
        return page.locator(
            'input[type="submit"], button:has-text("' + SUBMIT_TEXT + '")'
        )

    def post_fill(self, page: "Page", answers: dict[str, Any]) -> None:
        """Greenhouse-specific cleanup between fill and submit (none today).

        Fallback select2 strategy is documented on the class docstring and
        handled by the shared extractor; the plugin surfaces the selectors.
        """


plugin = GreenhousePlugin()


# Self-registration (registry lands separately in the same wave; integration
# of this plugin happens once registry is on main).
try:  # noqa: SIM105 - guard ImportError, not a subtle control flow
    from auto_job_apply.services.ats_registry import registry

    _plugins = registry()
    if plugin not in _plugins:
        _plugins.append(plugin)
except (ImportError, AttributeError):  # pragma: no cover - registry races
    pass


__all__ = ["GreenhousePlugin", "plugin"]


def _query(page: "Page", selector: str) -> Any:
    """Return a clickable element for ``selector`` or None. Duck-typed."""
    if not hasattr(page, "query_selector"):
        return None
    return page.query_selector(selector)

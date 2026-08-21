"""Field extractor: Playwright-driven walk of an ATS application form.

Given a job URL, walk the live form and emit a normalized
:class:`ApplicationForm` with every field, its required-ness, and a stable
identity (``Field.key``). Extraction is scoped by the matched ATS plugin's
selectors with a generic label-driven fallback so unexpected fields are still
surfaced rather than silently skipped.

Design notes:
- ``Field.key`` is a stable hash of (normalized label, type) so the same
  logical field keeps identity across extractions.
- Discovery is iterative: after each pass the form is re-queried because
  answering/focusing earlier fields can reveal new ones (conditional blocks).
  A snapshot (screenshot + HTML) is captured per iteration via
  ``utils.artifacts.snapshot_page``.
- A hard wall-clock cap (``FILLER.timeout_ms``) bounds the walk; on any
  timeout/exception the partial form is raised inside
  ``ExtractionError.context["partial"]``.
- Radios sharing a ``name`` collapse into one ``radio`` field with options;
  checkboxes sharing a ``name`` collapse into one ``checkbox-group`` field
  with options. Lone checkboxes stay ``checkbox``.
- Hidden/submit/button inputs are skipped; unclassifiable visible inputs are
  surfaced as ``type="unknown"`` (flag everything; never drop silently).

The real browser is only touched inside :func:`_open_page`; tests inject a
fake page via the ``page_opener`` seam, so unit tests need no browser.
"""

from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Literal

from pydantic import BaseModel

from auto_job_apply.config import settings
from auto_job_apply.errors import ExtractionError
from auto_job_apply.services.ats_registry import ATSPlugin, plugin_for
from auto_job_apply.utils import artifacts

FieldType = Literal[
    "text",
    "textarea",
    "select",
    "radio",
    "checkbox",
    "checkbox-group",
    "date",
    "file",
    "unknown",
]

# Canonical separator for multi-value answers (checkbox-group). The planner
# prompt instructs the LLM to use it, the filler splits on it, and profile
# fixtures store it. ("pipe" wins over comma/semicolon because option labels
# legitimately contain both of the latter.)
MULTI_VALUE_SEP = "|"

# input[type=...] values mapped onto the normalized FieldType vocabulary.
_INPUT_TYPE_MAP: dict[str, FieldType] = {
    "text": "text",
    "email": "text",
    "tel": "text",
    "url": "text",
    "number": "text",
    "search": "text",
    "password": "text",
    "date": "date",
    "datetime-local": "date",
    "file": "file",
}

_SKIP_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}

# Selectors used for the DOM walk (constants so tests can route fakes).
SEL_FORM_FALLBACK = "form"
SEL_TEXT_INPUTS = (
    'input:not([type]), input[type="text"], input[type="email"], '
    'input[type="tel"], input[type="url"], input[type="number"], '
    'input[type="search"], input[type="password"]'
)
SEL_TEXTAREAS = "textarea"
SEL_SELECTS = "select"
SEL_DATES = 'input[type="date"], input[type="datetime-local"]'
SEL_FILES = 'input[type="file"]'
SEL_RADIOS = 'input[type="radio"]'
SEL_CHECKBOXES = 'input[type="checkbox"]'
SEL_OTHER_INPUTS = "input"

MAX_ITERATIONS = 5


class Field(BaseModel):
    """One normalized form field."""

    key: str
    label: str
    type: FieldType
    required: bool = False
    options: list[str] | None = None
    answer: str | None = None
    submitted: bool = False


class ApplicationForm(BaseModel):
    """Normalized extraction result for one application form."""

    url: str
    ats_type: str
    fields: list[Field]
    discovered_iterations: int = 0


def _normalize_label(label: str) -> str:
    return " ".join(label.split()).strip().lower()


def field_key(label: str, ftype: str) -> str:
    """Stable identity for a logical field: hash of (normalized label, type)."""
    digest = hashlib.sha256(f"{_normalize_label(label)}|{ftype}".encode())
    return digest.hexdigest()[:16]


def _filler_timeout_ms() -> int:
    return int(settings.get("FILLER.timeout_ms", 45_000))


def _filler_headless() -> bool:
    return bool(settings.get("FILLER.headless", True))


@contextmanager
def _open_page(url: str, headless: bool, timeout_ms: int) -> Iterator[Any]:
    """Open ``url`` in a real headless/headed Chromium page."""
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


# --- DOM walk helpers (narrow element surface: get_attribute/inner_text/ ---
# --- evaluate/locator) so tests can substitute fakes. ---------------------


def _attr(el: Any, name: str) -> str | None:
    value = el.get_attribute(name)
    return value if value else None


def _label_for(scope: Any, el: Any) -> str:
    """Resolve a human-readable label for a control, best-first."""
    aria = _attr(el, "aria-label")
    if aria:
        return aria.strip()
    el_id = _attr(el, "id")
    if el_id:
        label = scope.locator(f'label[for="{el_id}"]')
        if label.count():
            text = label.first.inner_text().strip()
            if text:
                return text
    closest = el.evaluate(
        "el => { const l = el.closest('label'); return l ? l.innerText : null; }"
    )
    if closest and str(closest).strip():
        return str(closest).strip()
    placeholder = _attr(el, "placeholder")
    if placeholder:
        return placeholder.strip()
    name = _attr(el, "name")
    if name:
        return name.strip()
    return "unknown"


def _group_label(scope: Any, el: Any) -> str:
    """Label for a radio/checkbox group: fieldset legend, else member label."""
    legend = el.evaluate(
        "el => { const f = el.closest('fieldset');"
        " const l = f && f.querySelector('legend');"
        " return l ? l.innerText : null; }"
    )
    if legend and str(legend).strip():
        return str(legend).strip()
    return _label_for(scope, el)


def _is_required(label: str, el: Any) -> bool:
    """Required when the control/attrs say so or the label carries a '*'."""
    if el.get_attribute("required") is not None:
        # Boolean attribute: present (even as "") means required.
        return True
    if (el.get_attribute("aria-required") or "").lower() == "true":
        return True
    return label.rstrip().endswith("*") or "*" in label


def _select_options(el: Any) -> list[str]:
    return [opt.inner_text().strip() for opt in el.locator("option").all()]


def _group_by_name(elements: list[Any]) -> dict[str, list[Any]]:
    groups: dict[str, list[Any]] = {}
    for el in elements:
        groups.setdefault(_attr(el, "name") or f"__solo_{id(el)}", []).append(el)
    return groups


def _classify(el: Any) -> FieldType | None:
    """Map an ``<input>`` onto a FieldType; ``None`` means skip the control."""
    input_type = (_attr(el, "type") or "text").lower()
    if input_type in _SKIP_INPUT_TYPES:
        return None
    if input_type in ("radio", "checkbox"):
        return None  # handled by the group walk, not the generic pass
    return _INPUT_TYPE_MAP.get(input_type, "unknown")


def discover_fields(page: Any, plugin: ATSPlugin) -> list[Field]:
    """Walk the form DOM once and return the normalized fields found."""
    selectors = plugin.base_selectors()
    form_sel = selectors.get("form_root", SEL_FORM_FALLBACK)

    scope = page.locator(form_sel)
    if not scope.count():
        # Generic fallback: any <form>, then the whole page.
        scope = page.locator(SEL_FORM_FALLBACK)
        if not scope.count():
            scope = page

    fields: list[Field] = []

    def add(label: str, ftype: FieldType, required: bool, options: list[str] | None) -> None:
        fields.append(
            Field(
                key=field_key(label, ftype),
                label=label,
                type=ftype,
                required=required,
                options=options,
            )
        )

    for el in scope.locator(SEL_TEXT_INPUTS).all():
        label = _label_for(scope, el)
        add(label, "text", _is_required(label, el), None)
    for el in scope.locator(SEL_TEXTAREAS).all():
        label = _label_for(scope, el)
        add(label, "textarea", _is_required(label, el), None)
    for el in scope.locator(SEL_SELECTS).all():
        label = _label_for(scope, el)
        add(label, "select", _is_required(label, el), _select_options(el))
    for el in scope.locator(SEL_DATES).all():
        label = _label_for(scope, el)
        add(label, "date", _is_required(label, el), None)
    for el in scope.locator(SEL_FILES).all():
        label = _label_for(scope, el)
        add(label, "file", _is_required(label, el), None)

    for name, members in _group_by_name(scope.locator(SEL_RADIOS).all()).items():
        label = _group_label(scope, members[0])
        options = [_label_for(scope, m) for m in members]
        required = _is_required(label, members[0]) or any(
            _is_required(_label_for(scope, m), m) for m in members
        )
        add(label, "radio", required, options)

    for name, members in _group_by_name(scope.locator(SEL_CHECKBOXES).all()).items():
        solo = len(members) == 1
        label = _label_for(scope, members[0]) if solo else _group_label(scope, members[0])
        options = None if solo else [_label_for(scope, m) for m in members]
        required = _is_required(label, members[0]) or any(
            _is_required(_label_for(scope, m), m) for m in members
        )
        add(label, "checkbox" if solo else "checkbox-group", required, options)

    # Flag-everything pass: visible inputs of unmapped types surface as
    # "unknown" so the review layer sees them instead of dropping them.
    known = set(_INPUT_TYPE_MAP) | _SKIP_INPUT_TYPES | {"radio", "checkbox"}
    for el in scope.locator(SEL_OTHER_INPUTS).all():
        input_type = (_attr(el, "type") or "text").lower()
        if input_type in known:
            continue
        label = _label_for(scope, el)
        add(label, "unknown", _is_required(label, el), None)

    return fields


def extract(
    url: str,
    *,
    application_id: str = "extract",
    page_opener: Callable[[str, bool, int], Any] | None = None,
) -> ApplicationForm:
    """Walk the form at ``url`` and return a normalized ``ApplicationForm``.

    Raises:
        UnsupportedATSError: when no plugin claims the URL (propagated from
            the registry).
        ExtractionError: on timeout or unexpected failure. When any fields or
            snapshots were captured before the failure, the partial form is
            available at ``exc.context["partial"]``.
    """
    plugin = plugin_for(url)
    opener = page_opener or _open_page
    timeout_ms = _filler_timeout_ms()
    deadline = time.monotonic() + timeout_ms / 1000.0

    fields: dict[str, Field] = {}
    snapshots: list[Any] = []
    iterations = 0
    error: Exception | None = None

    try:
        with opener(url, _filler_headless(), timeout_ms) as page:
            plugin.pre_extract(page)
            while iterations < MAX_ITERATIONS:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"extraction exceeded FILLER.timeout_ms={timeout_ms}"
                    )
                iterations += 1
                for field in discover_fields(page, plugin):
                    fields.setdefault(field.key, field)
                snapshots.extend(
                    artifacts.snapshot_page(application_id, page, f"extract-iter{iterations}")
                )
                if iterations > 1 and len(fields) == prev_count:
                    break
                prev_count = len(fields)
    except Exception as exc:  # noqa: BLE001 — partial form must survive any failure
        error = exc

    if error is not None:
        partial = ApplicationForm(
            url=url,
            ats_type=plugin.name,
            fields=list(fields.values()),
            discovered_iterations=iterations,
        )
        raise ExtractionError(
            f"Extraction failed for {url}: {error}",
            context={
                "url": url,
                "ats_type": plugin.name,
                "partial": partial,
                "snapshots": [str(p) for p in snapshots],
                "cause": str(error),
            },
        ) from error

    return ApplicationForm(
        url=url,
        ats_type=plugin.name,
        fields=list(fields.values()),
        discovered_iterations=iterations,
    )


__all__ = [
    "ApplicationForm",
    "Field",
    "FieldType",
    "MULTI_VALUE_SEP",
    "discover_fields",
    "extract",
    "field_key",
]

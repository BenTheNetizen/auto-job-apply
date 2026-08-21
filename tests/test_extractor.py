"""Unit tests for services/extractor.py.

All DOM access runs through narrow fakes (FakePage/FakeLocator/FakeElement) —
no real browser is launched. The real-browser seam (``_open_page``) is
exercised only indirectly via the ``page_opener`` injection point.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from auto_job_apply.errors import ExtractionError, UnsupportedATSError
from auto_job_apply.services import extractor
from auto_job_apply.services.extractor import (
    ApplicationForm,
    Field,
    discover_fields,
    extract,
    field_key,
)


# --- Fakes -----------------------------------------------------------------


class FakeLocator:
    def __init__(self, elements: list[Any]) -> None:
        self._elements = elements

    def all(self) -> list[Any]:
        return list(self._elements)

    def count(self) -> int:
        return len(self._elements)

    @property
    def first(self) -> Any:
        return self._elements[0]


class FakeElement:
    """Narrow surface used by the extractor: get_attribute/inner_text/"""

    def __init__(
        self,
        attrs: dict[str, str] | None = None,
        text: str = "",
        closest_label: str | None = None,
        closest_legend: str | None = None,
        options: list[str] | None = None,
    ) -> None:
        self.attrs = attrs or {}
        self.text = text
        self.closest_label = closest_label
        self.closest_legend = closest_legend
        self._options = options or []

    def get_attribute(self, name: str) -> str | None:
        return self.attrs.get(name)

    def inner_text(self) -> str:
        return self.text

    def evaluate(self, script: str) -> str | None:
        if "closest('fieldset')" in script:
            return self.closest_legend
        if "closest('label')" in script:
            return self.closest_label
        raise AssertionError(f"unexpected evaluate script: {script}")

    def locator(self, selector: str) -> FakeLocator:
        if selector == "option":
            return FakeLocator([FakeElement(text=o) for o in self._options])
        raise AssertionError(f"unexpected element locator: {selector}")


class FakePage:
    """Routes ``locator(selector)`` to canned element lists.

    ``controls`` maps the extractor's selector constants to element lists;
    a value may also be a zero-arg callable returning a list (invoked per
    query, so tests can simulate fields appearing on later passes).
    ``labels`` maps element ids to their ``<label for=...>`` text.
    """

    def __init__(
        self,
        controls: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        self.controls = controls or {}
        self.labels = labels or {}

    def locator(self, selector: str) -> FakeLocator:
        if selector.startswith('label[for="'):
            el_id = selector[len('label[for="') : -2]
            text = self.labels.get(el_id)
            return FakeLocator([FakeElement(text=text)] if text else [])
        value = self.controls.get(selector, [])
        if callable(value):
            value = value()
        return FakeLocator(value)


class _ScopeRoutingFakeLocator(FakeLocator):
    """Form-root locator that supports further .locator() scoping."""

    def __init__(self, page: FakePage) -> None:
        super().__init__([FakeElement()])
        self._page = page

    def locator(self, selector: str) -> FakeLocator:
        return self._page.locator(selector)


def _page(
    controls: dict[str, Any],
    labels: dict[str, str] | None = None,
    has_form: bool = True,
) -> FakePage:
    """FakePage whose form-root locator supports nested scoping."""
    page = FakePage(controls, labels)
    original = page.locator

    def routing(selector: str) -> FakeLocator:
        if selector == "form":
            if not has_form:
                return FakeLocator([])
            return _ScopeRoutingFakeLocator(page)
        return original(selector)

    page.locator = routing  # type: ignore[method-assign]
    return page


class FakePlugin:
    name = "ashby"

    def __init__(self) -> None:
        self.pre_extract_calls = 0

    def base_selectors(self) -> dict[str, str]:
        return {"form_root": "form"}

    def pre_extract(self, page: Any) -> None:
        self.pre_extract_calls += 1


@contextmanager
def _nullctx(page: Any):
    yield page


def _opener(page: Any):
    def open_(url: str, headless: bool, timeout_ms: int):
        return _nullctx(page)

    return open_


@pytest.fixture()
def stub_plugin(monkeypatch: pytest.MonkeyPatch) -> FakePlugin:
    plugin = FakePlugin()
    monkeypatch.setattr(extractor, "plugin_for", lambda url: plugin)
    return plugin


@pytest.fixture()
def no_snapshots(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def fake_snapshot(application_id: str, page: Any, prefix: str = "snapshot"):
        calls.append((application_id, prefix))
        return []

    monkeypatch.setattr(extractor.artifacts, "snapshot_page", fake_snapshot)
    return calls


def text_input(id_: str, required: bool = False, **attrs: str) -> FakeElement:
    a = {"id": id_, "type": "text", **attrs}
    if required:
        a["required"] = ""
    return FakeElement(attrs=a)


# --- Field key / model ------------------------------------------------------


class TestFieldKey:
    def test_stable_for_same_label_and_type(self) -> None:
        assert field_key("Full Name", "text") == field_key("Full Name", "text")

    def test_normalized_case_and_whitespace(self) -> None:
        assert field_key("  Full   Name ", "text") == field_key("full name", "text")

    def test_type_changes_key(self) -> None:
        assert field_key("Bio", "text") != field_key("Bio", "textarea")

    def test_model_defaults(self) -> None:
        f = Field(key=field_key("X", "text"), label="X", type="text")
        assert f.required is False
        assert f.answer is None
        assert f.submitted is False


# --- discover_fields --------------------------------------------------------


class TestDiscoverFields:
    def test_text_input_with_label_for_and_required_attr(self) -> None:
        el = text_input("full-name", required=True)
        page = _page(
            {extractor.SEL_TEXT_INPUTS: [el]}, labels={"full-name": "Full Name"}
        )
        fields = discover_fields(page, FakePlugin())
        assert len(fields) == 1
        f = fields[0]
        assert (f.label, f.type, f.required) == ("Full Name", "text", True)
        assert f.key == field_key("Full Name", "text")

    def test_textarea_via_aria_label(self) -> None:
        el = FakeElement(attrs={"aria-label": "Why are you a good fit?"})
        page = _page({extractor.SEL_TEXTAREAS: [el]})
        (f,) = discover_fields(page, FakePlugin())
        assert (f.type, f.label, f.required) == ("textarea", "Why are you a good fit?", False)

    def test_required_from_label_asterisk(self) -> None:
        el = FakeElement(attrs={}, closest_label="Email *")
        page = _page({extractor.SEL_TEXT_INPUTS: [el]})
        (f,) = discover_fields(page, FakePlugin())
        assert f.required is True and f.label == "Email *"

    def test_select_with_options(self) -> None:
        el = FakeElement(
            attrs={"aria-label": "Location"}, options=["NYC", "SF", "Remote"]
        )
        page = _page({extractor.SEL_SELECTS: [el]})
        (f,) = discover_fields(page, FakePlugin())
        assert (f.type, f.options) == ("select", ["NYC", "SF", "Remote"])

    def test_date_and_file(self) -> None:
        date = FakeElement(attrs={"type": "date", "aria-label": "Start date"})
        file_ = FakeElement(attrs={"type": "file", "aria-label": "Resume", "required": ""})
        page = _page({extractor.SEL_DATES: [date], extractor.SEL_FILES: [file_]})
        kinds = {f.type: f for f in discover_fields(page, FakePlugin())}
        assert kinds["date"].label == "Start date"
        assert kinds["file"].required is True

    def test_radios_collapse_to_one_field_with_options(self) -> None:
        yes = FakeElement(attrs={"type": "radio", "name": "sponsorship", "aria-label": "Yes"})
        no = FakeElement(attrs={"type": "radio", "name": "sponsorship", "aria-label": "No"})
        yes.closest_legend = "Do you need sponsorship? *"
        page = _page({extractor.SEL_RADIOS: [yes, no]})
        (f,) = discover_fields(page, FakePlugin())
        assert f.type == "radio"
        assert f.label == "Do you need sponsorship? *"
        assert f.required is True
        assert f.options == ["Yes", "No"]

    def test_checkboxes_group_and_solo(self) -> None:
        a = FakeElement(attrs={"type": "checkbox", "name": "langs", "aria-label": "Python"})
        b = FakeElement(attrs={"type": "checkbox", "name": "langs", "aria-label": "Go"})
        a.closest_legend = "Languages"
        solo = FakeElement(attrs={"type": "checkbox", "aria-label": "I agree"})
        page = _page({extractor.SEL_CHECKBOXES: [a, b, solo]})
        by_type = {f.type: f for f in discover_fields(page, FakePlugin())}
        assert by_type["checkbox-group"].options == ["Python", "Go"]
        assert by_type["checkbox-group"].label == "Languages"
        assert by_type["checkbox"].label == "I agree"
        assert by_type["checkbox"].options is None

    def test_hidden_and_submit_inputs_skipped_unknown_type_flagged(self) -> None:
        hidden = FakeElement(attrs={"type": "hidden", "name": "csrf"})
        submit = FakeElement(attrs={"type": "submit"})
        weird = FakeElement(attrs={"type": "color", "aria-label": "Favorite color"})
        page = _page({extractor.SEL_OTHER_INPUTS: [hidden, submit, weird]})
        (f,) = discover_fields(page, FakePlugin())
        assert f.type == "unknown" and f.label == "Favorite color"

    def test_fallback_to_page_scope_when_form_root_missing(self) -> None:
        el = FakeElement(attrs={"aria-label": "Name"})
        page = _page({extractor.SEL_TEXT_INPUTS: [el]}, has_form=False)
        (f,) = discover_fields(page, FakePlugin())
        assert f.label == "Name"


# --- extract ----------------------------------------------------------------


class TestExtract:
    def test_happy_path_single_iteration(
        self, stub_plugin: FakePlugin, no_snapshots: list[tuple[str, str]]
    ) -> None:
        el = text_input("full-name", required=True)
        page = _page(
            {extractor.SEL_TEXT_INPUTS: [el]}, labels={"full-name": "Full Name"}
        )
        form = extract(
            "https://jobs.ashbyhq.com/acme/123",
            page_opener=_opener(page),
        )
        assert isinstance(form, ApplicationForm)
        assert form.ats_type == "ashby"
        assert [f.label for f in form.fields] == ["Full Name"]
        assert form.fields[0].required is True
        # discovery converged: pass 2 saw no new fields
        assert form.discovered_iterations == 2
        assert stub_plugin.pre_extract_calls == 1
        assert ("extract", "extract-iter1") in no_snapshots

    def test_iterative_discovery_finds_new_fields(
        self, stub_plugin: FakePlugin, no_snapshots: list[tuple[str, str]]
    ) -> None:
        first = text_input("full-name")
        late = FakeElement(attrs={"aria-label": "Conditional question"})
        queries = {"n": 0}

        def provide_textareas() -> list[FakeElement]:
            # First discovery pass: hidden. Second pass onward: revealed.
            queries["n"] += 1
            return [] if queries["n"] == 1 else [late]

        page = _page(
            {extractor.SEL_TEXT_INPUTS: [first], extractor.SEL_TEXTAREAS: provide_textareas},
            labels={"full-name": "Full Name"},
        )
        form = extract("https://jobs.ashbyhq.com/acme/1", page_opener=_opener(page))
        labels = {f.label for f in form.fields}
        assert labels == {"Full Name", "Conditional question"}
        assert form.discovered_iterations == 3

    def test_failure_raises_with_partial(
        self, stub_plugin: FakePlugin, no_snapshots: list[tuple[str, str]]
    ) -> None:
        el = text_input("full-name")
        page = _page(
            {extractor.SEL_TEXT_INPUTS: [el]}, labels={"full-name": "Full Name"}
        )

        class BoomPage:
            """Wraps the fake page; blows up on the second snapshot pass."""

            def __init__(self, inner: FakePage) -> None:
                self._inner = inner
                self._calls = 0

            def locator(self, selector: str) -> Any:
                return self._inner.locator(selector)

            def screenshot(self) -> bytes:
                return b""

            def content(self) -> str:
                self._calls += 1
                if self._calls > 1:
                    raise RuntimeError("browser died mid-walk")
                return "<html></html>"

        snapshots: list[Any] = []

        def snap(application_id: str, page: Any, prefix: str = "snapshot"):
            page.content()  # raises on 2nd call
            snapshots.append(prefix)
            return []

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(extractor.artifacts, "snapshot_page", snap)
        try:
            with pytest.raises(ExtractionError) as exc_info:
                extract(
                    "https://jobs.ashbyhq.com/acme/9",
                    page_opener=_opener(BoomPage(page)),
                )
        finally:
            monkeypatch.undo()

        err = exc_info.value
        partial = err.context["partial"]
        assert isinstance(partial, ApplicationForm)
        assert [f.label for f in partial.fields] == ["Full Name"]
        assert err.context["url"] == "https://jobs.ashbyhq.com/acme/9"
        assert "browser died" in err.context["cause"]

    def test_unsupported_url_propagates(self) -> None:
        # Real registry: no plugin claims example.com.
        with pytest.raises(UnsupportedATSError) as exc_info:
            extract("https://example.com/jobs/1")
        assert exc_info.value.context["url"] == "https://example.com/jobs/1"


class TestRegistryIntegration:
    """Cheap integration: the real registry routes to the real plugins."""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://jobs.ashbyhq.com/acme/123", "ashby"),
            ("https://boards.greenhouse.io/acme/456", "greenhouse"),
            ("https://jobs.lever.co/acme/789", "lever"),
        ],
    )
    def test_plugin_for_routes(self, url: str, expected: str) -> None:
        from auto_job_apply.services.ats_registry import plugin_for

        assert plugin_for(url).name == expected

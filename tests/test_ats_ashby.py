"""Unit tests for the Ashby ATS plugin.

Detection matrix, dispatch through the registry, selector-copy isolation,
cookie-banner dismissal, and submit-button locator construction. Integration
against the eval mock ``/ashby`` route is owned by the eval-runner leaf; these
tests mirror the mock's DOM shape with small fakes.
"""

from __future__ import annotations

import pytest

from auto_job_apply.errors import UnsupportedATSError
from auto_job_apply.services import ats_registry
from auto_job_apply.services.ats import ashby
from auto_job_apply.services.ats.ashby import SUBMIT_TEXT, plugin


class TestDetectionMatrix:
    @pytest.mark.parametrize(
        "url",
        [
            "https://jobs.ashbyhq.com/acme/abc123",
            "https://ashbyhq.com/acme/abc123",
            "https://foo.jobs.ashbyhq.com/x",
            "https://foo.ashbyhq.com/x",
        ],
    )
    def test_detects_ashby_hosts(self, url: str) -> None:
        assert plugin.detect(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://boards.greenhouse.io/acme/123",
            "https://jobs.lever.co/acme/123",
            "https://ashbyhq.com.evil.example.org/x",
            "https://example.com/ashbyhq.com",
            "",
            "not a url",
        ],
    )
    def test_rejects_non_ashby_hosts(self, url: str) -> None:
        assert not plugin.detect(url)


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Snapshot the global plugin registry to keep tests hermetic."""
    plugins = ats_registry.registry()
    saved = list(plugins)
    plugins.clear()
    yield
    plugins.clear()
    plugins.extend(saved)


class TestDispatch:
    def test_registry_returns_ashby_plugin_for_jobs_url(self) -> None:
        ats_registry.register(plugin)
        resolved = ats_registry.plugin_for("https://jobs.ashbyhq.com/acme/abc")
        assert resolved is plugin
        assert resolved.name == "ashby"

    def test_unknown_host_raises_unsupported_ats(self) -> None:
        with pytest.raises(UnsupportedATSError) as excinfo:
            ats_registry.plugin_for("https://unknown-ats.example.org/job/1")
        assert "unknown-ats.example.org" in excinfo.value.url


class TestBaseSelectors:
    def test_required_keys_present(self) -> None:
        selectors = plugin.base_selectors()
        assert selectors["form_root"] == "form"
        assert selectors["label"] == "label"
        assert selectors["select"] == "select"
        assert selectors["file"] == "input[type=file]"
        assert "checkbox" in selectors["checkbox_or_radio"]
        assert "radio" in selectors["checkbox_or_radio"]

    def test_returns_a_copy(self) -> None:
        selectors = plugin.base_selectors()
        selectors["form_root"] = "MUTATED"
        assert plugin.base_selectors()["form_root"] == "form"


class FakeLocator:
    """Minimal Locator double sufficient for abusing ashby plugin helpers."""

    def __init__(self, texts: list[str] | None = None, visible: bool = True):
        self._texts = texts or []
        self._visible = visible
        self.clicks = 0
        self._parent = None

    def count(self) -> int:
        return len(self._texts)

    @property
    def first(self) -> "FakeLocator":
        inner = FakeLocator(self._texts[:1], self._visible)
        inner._parent = self
        return inner


    def is_visible(self) -> bool:
        return self._visible and bool(self._texts)

    def click(self) -> None:
        self.clicks += 1
        if self._parent is not None:
            self._parent.clicks += 1

    def filter(self, has_text=None) -> "FakeLocator":
        if has_text is None:
            return FakeLocator(list(self._texts), self._visible)
        matched = [t for t in self._texts if has_text.search(t)]
        return FakeLocator(matched, self._visible)

    def or_(self, other: "FakeLocator") -> "FakeLocator":
        combined = list(self._texts) + list(other._texts)
        return FakeLocator(combined, self._visible)

    def matched_texts(self) -> list[str]:
        return list(self._texts)


class FakePage:
    """Playwright page double with per-selector locator fakes."""

    def __init__(
        self,
        locator_map: dict[str, FakeLocator] | None = None,
        role_button_texts: list[str] | None = None,
    ) -> None:
        self._locator_map = locator_map or {}
        self._role_button_texts = role_button_texts or []

    def locator(self, css: str) -> FakeLocator:
        return self._locator_map.get(css, FakeLocator())

    def get_by_role(self, role: str, name=None) -> FakeLocator:
        if role != "button":
            return FakeLocator()
        texts = self._role_button_texts
        if name is not None:
            texts = [t for t in texts if name.search(t)]
        return FakeLocator(texts)


class TestPreExtract:
    def test_dismisses_cookie_banner(self) -> None:
        accept = FakeLocator(["Accept"], visible=True)
        page = FakePage(locator_map={'button:has-text("Accept")': accept})
        plugin.pre_extract(page)
        assert accept.clicks == 1

    def test_no_banner_is_a_no_op(self) -> None:
        page = FakePage(locator_map={})
        plugin.pre_extract(page)  # must not raise

    def test_invisible_banner_not_clicked(self) -> None:
        accept = FakeLocator(["Accept"], visible=False)
        page = FakePage(locator_map={'button:has-text("Accept")': accept})
        plugin.pre_extract(page)
        assert accept.clicks == 0


class TestSubmitButton:
    def test_matches_mock_submit_application(self) -> None:
        page = FakePage(role_button_texts=["Submit Application"])
        locator = plugin.submit_button(page)
        texts = locator.matched_texts()
        assert any(SUBMIT_TEXT.search(t) for t in texts)

    def test_matches_plain_submit(self) -> None:
        page = FakePage(role_button_texts=["Submit"])
        locator = plugin.submit_button(page)
        texts = locator.matched_texts()
        assert any(SUBMIT_TEXT.search(t) for t in texts)

    def test_submit_text_regex(self) -> None:
        assert SUBMIT_TEXT.search("Submit Application")
        assert SUBMIT_TEXT.search("Submit")
        assert not SUBMIT_TEXT.search("Cancel")


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__]))

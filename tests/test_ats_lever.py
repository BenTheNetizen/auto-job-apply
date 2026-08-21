"""Unit tests for the Lever ATS plugin.

The plugin self-registers on import through ``services.ats_registry.register``.
Detection asserts use the real plugin wired through ``plugin_for`` (which
lazy-imports the ``services.ats`` package). ``FakePage``/``FakeLocator``
record locator requests and clicks so selector strategy is testable without
a browser.
"""

from __future__ import annotations

import pytest

from auto_job_apply.errors import UnsupportedATSError
from auto_job_apply.services import ats_registry
from auto_job_apply.services.ats.lever import LeverPlugin, plugin as lever_plugin


POSITIVE_URLS = [
    "https://jobs.lever.co/acme/dead-uuid-here",
    "https://jobs.lever.co/acme/1234",
]

NEGATIVE_URLS = [
    "https://example.com/jobs/1",
    "https://jobs.not-lever.co/acme/1",  # suffix lookalike must not match
    "https://lever.co/acme/1",
]


class FakeLocator:
    """Playwright-lite locator shim: records ``click()`` on the page."""

    def __init__(self, page, selector, count=0, fail_nth=None):
        self._page = page
        self._selector = selector
        self._count = count
        self._fail_nth = fail_nth

    def count(self):
        return self._count

    def nth(self, i):
        if self._fail_nth == i:
            raise RuntimeError("detached element")
        return _Clickable(self._page, self._selector)


class _Clickable:
    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    def click(self):
        self._page.clicked.append(self._selector)


class FakePage:
    """Records every ``locator()`` request; per-selector counts."""

    def __init__(self, counts=None, fail_nth=None):
        self._counts = counts or {}
        self._fail_nth = fail_nth
        self.requested = []
        self.clicked = []

    def locator(self, selector):
        self.requested.append(selector)
        return FakeLocator(
            self,
            selector,
            count=self._counts.get(selector, 0),
            fail_nth=self._fail_nth,
        )


@pytest.fixture()
def clean_registry():
    """Isolate module-global plugin registry between tests."""
    saved = ats_registry._PLUGINS.copy()
    saved_flag = ats_registry._plugins_loaded
    ats_registry._PLUGINS.clear()
    yield
    ats_registry._PLUGINS.clear()
    ats_registry._PLUGINS.extend(saved)
    ats_registry._plugins_loaded = saved_flag


@pytest.fixture()
def plugin(clean_registry):
    """Re-register the real Lever plugin after registry isolation."""
    ats_registry.register(lever_plugin)
    return lever_plugin


class TestDetection:
    @pytest.mark.parametrize("url", POSITIVE_URLS)
    def test_detect_positive(self, plugin, url):
        found = ats_registry.plugin_for(url)
        assert found.name == "lever"
        assert isinstance(found, LeverPlugin)

    @pytest.mark.parametrize("url", NEGATIVE_URLS)
    def test_detect_negative(self, plugin, url):
        with pytest.raises(UnsupportedATSError):
            ats_registry.plugin_for(url)

    def test_self_registered_plugin(self, plugin):
        assert plugin.name == "lever"
        assert isinstance(plugin, LeverPlugin)


class TestSelectors:
    def test_base_selectors_shape(self):
        selectors = lever_plugin.base_selectors()
        assert all(isinstance(v, str) for v in selectors.values())
        for key in ("form_root", "accordion_toggle", "label", "required_marker"):
            assert key in selectors
        assert "application-form" in selectors["form_root"]

    def test_submit_button_locator_string(self):
        page = FakePage()
        result = lever_plugin.submit_button(page)
        assert result is not None
        (selector,) = page.requested
        assert "button[type=submit]" in selector
        assert "Submit" in selector


class TestPreExtract:
    def test_no_toggles_is_noop(self):
        page = FakePage()
        lever_plugin.pre_extract(page)
        assert page.clicked == []

    def test_clicks_each_toggle_once(self):
        page = FakePage(counts={".toggle": 3})
        lever_plugin.pre_extract(page)
        assert page.clicked == [".toggle", ".toggle", ".toggle"]

    def test_click_failure_tolerated(self):
        page = FakePage(counts={".toggle": 2}, fail_nth=1)
        lever_plugin.pre_extract(page)
        assert page.clicked == [".toggle"]


class TestPostFill:
    def test_noop(self):
        assert lever_plugin.post_fill(FakePage(), {}) is None

"""Unit tests for the Greenhouse ATS plugin.

Contract-only: no Playwright dependency; uses fakes for page behavior.
"""

from __future__ import annotations

import pytest

from auto_job_apply.services.ats import greenhouse


class FakeElement:
    def __init__(self, selector: str) -> None:
        self.selector = selector
        self.clicked = 0

    def click(self) -> None:
        self.clicked += 1


class FakePage:
    def __init__(self, elements: dict[str, bool] | None = None) -> None:
        self._elements = elements or {}
        self.requested = []

    def query_selector(self, selector: str):
        self.requested.append(selector)
        if self._elements.get(selector, False):
            return FakeElement(selector)
        return None

    def locator(self, selector: str):
        self.requested.append(selector)
        return FakeElement(selector)


@pytest.fixture(name="plugin")
def plugin_from_module():
    return greenhouse.plugin


class TestDetect:
    def test_positive_canonical(self, plugin):
        assert plugin.detect("https://boards.greenhouse.io/org") is True

    def test_positive_deep_path(self, plugin):
        assert plugin.detect("https://boards.greenhouse.io/org/jobs?id=123") is True

    def test_negative_similar_host_ignored(self, plugin):
        assert plugin.detect("https://boards.greenhouse.io.evil.com/x") is False

    def test_negative_other_ats(self, plugin):
        assert plugin.detect("https://jobs.lever.co/org/1") is False

    def test_negative_bare_domain(self, plugin):
        # urlparse treats this as a path, not host; extractor always hands
        # a full URL.
        assert plugin.detect("boards.greenhouse.io") is False


class TestBaseSelectors:
    def test_shape(self, plugin):
        selectors = plugin.base_selectors()
        assert selectors["form"] == "#application form"
        assert selectors["required_label_marker"] == "span.asterisk"
        assert selectors["required_attr_marker"] == "[required]"
        assert "select2_widget" in selectors
        assert selectors["select"] == "select"


class TestPreExtract:
    def test_dismisses_cookie_modal_when_present(self, plugin):
        page = FakePage({'button:has-text("Accept")': True})
        plugin.pre_extract(page)
        # Only one selector asked; click issued on the found element.
        assert page.requested[0] == 'button:has-text("Accept")'

    def test_expands_demographic_section(self, plugin):
        page = FakePage({".expand_all": True})
        plugin.pre_extract(page)
        assert ".expand_all" in page.requested

    def test_no_modal_or_accordion_ok(self, plugin):
        page = FakePage()
        plugin.pre_extract(page)  # must not raise

    def test_page_without_query_selector_tolerated(self, plugin):
        plugin.pre_extract(object())  # duck-typed guard, no raise


class TestSubmitButton:
    def test_asks_for_input_submit_or_text_button(self, plugin):
        page = FakePage()
        plugin.submit_button(page)
        selector = page.requested[-1]
        assert 'input[type="submit"]' in selector
        assert 'button:has-text("Submit")' in selector


class TestPluginSingleton:
    def test_module_exposes_singleton(self, plugin):
        assert green_note(plugin.name)
        assert plugin is greenhouse.plugin

    def test_plugin_protocol_shape(self, plugin):
        for method in (
            "detect",
            "base_selectors",
            "pre_extract",
            "submit_button",
            "post_fill",
        ):
            assert callable(getattr(plugin, method)), method


def green_note(name: str) -> bool:
    return isinstance(name, str) and name == "greenhouse"


class TestPostFill:
    def test_post_fill_no_op(self, plugin):
        # post_fill is a hook for future Greenhouse quirks; treat as no-op.
        plugin.post_fill(object(), {"x": 1})

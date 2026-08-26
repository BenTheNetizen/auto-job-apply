"""Unit tests for the ATS plugin registry.

Detection matrix uses stub plugins implementing the ``ATSPlugin`` protocol;
the real per-ATS plugins land in ``services/ats/*.py`` (owned by the
ats-plugins leaves) and self-register the same way these stubs do.
"""

from __future__ import annotations

from typing import Any

import pytest

from auto_job_apply.errors import UnsupportedATSError
from auto_job_apply.services import ats_registry
from auto_job_apply.services.ats_registry import (
    ATS_HOST_PATTERNS,
    ATSPlugin,
    hostname_matches,
    plugin_for,
    register,
    registry,
)


class StubPlugin:
    """Minimal ``ATSPlugin`` implementation backed by host patterns."""

    def __init__(self, name: str, patterns: tuple[str, ...]) -> None:
        self.name = name
        self.patterns = patterns

    def detect(self, url: str) -> bool:
        return hostname_matches(url, self.patterns)

    def base_selectors(self) -> dict[str, str]:
        return {"form": "form"}

    def submit_button(self, page: Any) -> Any:
        return page

    def pre_extract(self, page: Any) -> None:
        return None

    def post_fill(self, page: Any, answers: Any) -> None:
        return None

    def confirm_submission(self, page: Any) -> Any:
        """Minimal plugin stub satisfies the extended protocol."""
        from auto_job_apply.services.confirmation import SubmissionConfirmation

        return SubmissionConfirmation.UNKNOWN


@pytest.fixture()
def clean_registry():
    """Isolate module-global registry state per test."""
    saved = ats_registry._PLUGINS.copy()
    ats_registry._PLUGINS.clear()
    yield
    ats_registry._PLUGINS.clear()
    ats_registry._PLUGINS.extend(saved)


@pytest.fixture()
def plugins(clean_registry):
    """Three stub plugins mirroring the real host patterns."""
    stubs = [
        StubPlugin(name, patterns)
        for name, patterns in ATS_HOST_PATTERNS.items()
    ]
    for stub in stubs:
        register(stub)
    return stubs


DETECTION_MATRIX = [
    ("ashby", "https://jobs.ashbyhq.com/acme/1ab2c3"),
    ("ashby", "https://www.ashbyhq.com/acme/1ab2c3"),
    ("greenhouse", "https://boards.greenhouse.io/acme/jobs/1234"),
    ("lever", "https://jobs.lever.co/acme/dead-uuid-here"),
]

NEGATIVE_URLS = [
    "https://example.com/jobs/1",
    "https://linkedin.com/jobs/view/123",
    "https://workdayjobs.com/acme/job/1",
]


class TestHostPatterns:
    def test_matrix_positive(self) -> None:
        for ats_name, url in DETECTION_MATRIX:
            assert hostname_matches(url, ATS_HOST_PATTERNS[ats_name]), (ats_name, url)

    def test_matrix_negative(self) -> None:
        all_patterns = tuple(p for ps in ATS_HOST_PATTERNS.values() for p in ps)
        for url in NEGATIVE_URLS:
            assert not hostname_matches(url, all_patterns), url

    def test_subdomain_but_not_suffix_lookalike(self) -> None:
        # "not-ashbyhq.com" must not match "ashbyhq.com".
        assert not hostname_matches(
            "https://not-ashbyhq.com/x", ("ashbyhq.com",)
        )


class TestRegistry:
    def test_registry_returns_singleton_list(self, plugins) -> None:
        assert registry() is registry()
        assert [p.name for p in registry()] == ["ashby", "greenhouse", "lever"]

    def test_register_returns_plugin(self, clean_registry) -> None:
        stub = StubPlugin("ashby", ATS_HOST_PATTERNS["ashby"])
        assert register(stub) is stub
        assert registry() == [stub]

    @pytest.mark.parametrize("ats_name,url", DETECTION_MATRIX)
    def test_plugin_for_known_hosts(self, plugins, ats_name, url) -> None:
        assert plugin_for(url).name == ats_name

    def test_protocol_shape(self, plugins) -> None:
        plugin = plugins[0]
        assert isinstance(plugin.base_selectors(), dict)
        assert plugin.pre_extract(object()) is None
        assert plugin.post_fill(object(), {}) is None
        assert plugin.submit_button(object()) is not None
        # Protocol conformance is structural (duck-typed).
        assert all(hasattr(plugin, attr) for attr in ATSPlugin.__protocol_attrs__ | set())

    @pytest.mark.parametrize("url", NEGATIVE_URLS)
    def test_unknown_host_raises_with_context(self, plugins, url) -> None:
        with pytest.raises(UnsupportedATSError) as exc_info:
            plugin_for(url)
        err = exc_info.value
        assert err.context["url"] == url
        assert err.url == url
        assert url in str(err)

    def test_no_plugins_everything_unsupported(self, clean_registry) -> None:
        with pytest.raises(UnsupportedATSError) as exc_info:
            plugin_for("https://jobs.ashbyhq.com/acme/1")
        assert exc_info.value.context["url"] == "https://jobs.ashbyhq.com/acme/1"

    def test_lazy_plugin_load_tolerates_missing_ats_package(
        self, clean_registry
    ) -> None:
        # services/ats does not exist yet; load is a graceful no-op.
        ats_registry._ensure_plugins_loaded()
        assert registry() == []

"""ATS plugin registry.

Maps a job URL to its ATS plugin and defines the ``ATSPlugin`` protocol that
the per-ATS implementations (``services/ats/*.py``) satisfy. Plugins
self-register at import time; the registry lazily imports every module in the
``auto_job_apply.services.ats`` package on first dispatch, so adding a new ATS
is exactly one file.

Note on ``Locator``: Playwright is imported only under ``TYPE_CHECKING`` so
this module carries no hard Playwright dependency (added later by the
extractor/filler leaves).
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import urlparse

from auto_job_apply.errors import UnsupportedATSError

if TYPE_CHECKING:
    from playwright.sync_api import Locator

    from auto_job_apply.services.confirmation import SubmissionConfirmation

ATSType = Literal["ashby", "greenhouse", "lever"]

# Host patterns per ATS. Plugin ``detect`` implementations should reuse these
# (also useful later for public-info endpoints).
ATS_HOST_PATTERNS: dict[ATSType, tuple[str, ...]] = {
    "ashby": ("ashbyhq.com", "jobs.ashbyhq.com"),
    "greenhouse": ("boards.greenhouse.io",),
    "lever": ("jobs.lever.co",),
}


class ATSPlugin(Protocol):
    """Contract every per-ATS plugin satisfies."""

    name: str

    def detect(self, url: str) -> bool: ...

    def base_selectors(self) -> dict[str, str]: ...

    def submit_button(self, page: Any) -> Locator: ...

    def pre_extract(self, page: Any) -> None:
        """Expand sections / dismiss banners before extraction."""
        ...

    def post_fill(self, page: Any, answers: Any) -> None: ...

    def confirm_submission(self, page: Any) -> "SubmissionConfirmation":
        """Post-click machine-check: redirect → toast → validation →
        bot → UNKNOWN. Composed via ``services.confirmation.confirm_by``.
        """
        ...


def hostname_matches(url: str, patterns: tuple[str, ...]) -> bool:
    """True when ``url``'s hostname equals or is a subdomain of any pattern."""
    hostname = urlparse(url).hostname or ""
    return any(
        hostname == pattern or hostname.endswith(f".{pattern}")
        for pattern in patterns
    )


_PLUGINS: list[ATSPlugin] = []
_plugins_loaded = False


def register(plugin: ATSPlugin) -> ATSPlugin:
    """Register a plugin singleton. Returns it for decorator-style use."""
    _PLUGINS.append(plugin)
    return plugin


def registry() -> list[ATSPlugin]:
    """The singleton list of registered plugin singletons.

    Do not mutate; use :func:`register` to add plugins.
    """
    return _PLUGINS


def _ensure_plugins_loaded() -> None:
    """Import every module in ``services/ats`` so plugins self-register.

    Idempotent; a missing ``services.ats`` package (before plugin leaves land)
    is tolerated — dispatch will simply report every URL as unsupported.
    """
    global _plugins_loaded
    if _plugins_loaded:
        return
    _plugins_loaded = True
    try:
        ats_pkg = importlib.import_module("auto_job_apply.services.ats")
    except ModuleNotFoundError:
        return
    for module_info in pkgutil.iter_modules(ats_pkg.__path__):
        importlib.import_module(f"{ats_pkg.__name__}.{module_info.name}")


def plugin_for(url: str) -> ATSPlugin:
    """Return the plugin whose ``detect`` matches ``url``.

    Raises:
        UnsupportedATSError: when no registered plugin claims the URL. The
            URL is available on ``.url`` and in ``.context["url"]``.
    """
    _ensure_plugins_loaded()
    for plugin in _PLUGINS:
        if plugin.detect(url):
            return plugin
    raise UnsupportedATSError(url)


__all__ = [
    "ATSType",
    "ATSPlugin",
    "ATS_HOST_PATTERNS",
    "hostname_matches",
    "register",
    "registry",
    "plugin_for",
]

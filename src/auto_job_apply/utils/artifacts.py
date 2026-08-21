"""Artifact writer for screenshots, HTML dumps, and error dumps.

Artifacts live under ``${DATA.dir}/artifacts/<application_id>/``. Application
ids and artifact names are validated to be path-safe.

The Playwright ``Page`` type is imported under ``TYPE_CHECKING`` only, so this
module has no runtime dependency on Playwright; any object with
``screenshot() -> bytes`` and ``content() -> str`` works.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from auto_job_apply.config import settings
from auto_job_apply.errors import AutoJobApplyError

if TYPE_CHECKING:
    from playwright.sync_api import Page

_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_id(application_id: str) -> None:
    if not _ID_RE.match(application_id):
        raise AutoJobApplyError(
            f"Invalid application id (must match [A-Za-z0-9-]+): {application_id!r}",
            context={"application_id": application_id},
        )


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name) or ".." in name:
        raise AutoJobApplyError(
            f"Invalid artifact name: {name!r}",
            context={"name": name},
        )


def _data_dir() -> Path:
    return Path(str(settings.get("DATA.dir", "data")))


def _screenshots_enabled() -> bool:
    return bool(settings.get("FILLER.screenshots", True))


def artifact_dir(application_id: str) -> Path:
    """Create (if needed) and return the artifact dir for an application."""
    _validate_id(application_id)
    path = _data_dir() / "artifacts" / application_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_artifact(application_id: str, name: str, data: bytes | str) -> Path:
    """Write an artifact file and return its path.

    ``name`` must be a bare filename (path-safe, no separators/traversal);
    the caller picks the suffix to match the content type.
    """
    _validate_name(name)
    path = artifact_dir(application_id) / name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


def snapshot_page(application_id: str, page: Page, prefix: str = "snapshot") -> list[Path]:
    """Capture a Playwright screenshot + HTML dump for the current page.

    Returns the written paths (PNG first, HTML second). Honors
    ``FILLER.screenshots`` — when disabled, writes nothing and returns [].
    """
    if not _screenshots_enabled():
        return []
    _validate_name(prefix)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    png = write_artifact(application_id, f"{prefix}-{stamp}.png", page.screenshot())
    html = write_artifact(application_id, f"{prefix}-{stamp}.html", page.content())
    return [png, html]


__all__ = ["artifact_dir", "write_artifact", "snapshot_page"]

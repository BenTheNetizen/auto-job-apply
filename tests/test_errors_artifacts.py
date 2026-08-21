"""Unit tests for the error taxonomy and artifact writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_job_apply.errors import (
    AutoJobApplyError,
    ConfigError,
    EmailPollError,
    ExtractionError,
    PlannerError,
    SubmissionError,
    UnsupportedATSError,
)
from auto_job_apply.utils import artifacts


class FakePage:
    """Duck-typed stand-in for playwright.sync_api.Page."""

    def __init__(self) -> None:
        self.screenshot_calls = 0

    def screenshot(self) -> bytes:
        self.screenshot_calls += 1
        return b"\x89PNG-fake-bytes"

    def content(self) -> str:
        return "<html><body>fake form</body></html>"


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect artifacts into a per-test tmp dir."""
    monkeypatch.setattr(artifacts, "_data_dir", lambda: tmp_path)
    return tmp_path


# --- errors -----------------------------------------------------------------


def test_all_errors_importable_in_one_line() -> None:
    import auto_job_apply.errors as e

    for name in e.__all__:
        assert issubclass(getattr(e, name), AutoJobApplyError)


def test_context_survives_raise_and_str() -> None:
    with pytest.raises(ExtractionError) as exc_info:
        raise ExtractionError("boom", context={"partial": {"fields": [1, 2]}})
    err = exc_info.value
    assert str(err) == "boom"
    assert err.context == {"partial": {"fields": [1, 2]}}


def test_base_error_defaults_to_empty_context() -> None:
    assert AutoJobApplyError("x").context == {}


def test_context_is_copied_not_aliased() -> None:
    src = {"a": 1}
    err = PlannerError("x", context=src)
    src["b"] = 2
    assert err.context == {"a": 1}


def test_unsupported_ats_error_carries_url() -> None:
    err = UnsupportedATSError("https://example.com/apply")
    assert err.url == "https://example.com/apply"
    assert err.context["url"] == "https://example.com/apply"
    assert "https://example.com/apply" in str(err)


def test_submission_error_carries_fields_missing() -> None:
    err = SubmissionError(["veteran_status", "visa"])
    assert err.fields_missing == ["veteran_status", "visa"]
    assert err.context["fields_missing"] == ["veteran_status", "visa"]
    assert "veteran_status" in str(err)


def test_submission_error_allows_custom_message_and_context() -> None:
    err = SubmissionError(message="network down", context={"attempt": 2})
    assert err.fields_missing == []
    assert err.context == {"fields_missing": [], "attempt": 2}
    assert str(err) == "network down"


def test_simple_subclasses_constructible() -> None:
    for cls in (ConfigError, ExtractionError, PlannerError, EmailPollError):
        assert cls("m").context == {}


# --- artifacts ---------------------------------------------------------------


def test_artifact_dir_created(tmp_path: Path) -> None:
    d = artifacts.artifact_dir("app-123")
    assert d == tmp_path / "artifacts" / "app-123"
    assert d.is_dir()


@pytest.mark.parametrize("bad_id", ["", "../evil", "a/b", "a b", "a_b", "x\\y"])
def test_artifact_dir_rejects_unsafe_ids(bad_id: str) -> None:
    with pytest.raises(AutoJobApplyError):
        artifacts.artifact_dir(bad_id)


def test_write_artifact_str_and_bytes(tmp_path: Path) -> None:
    text_path = artifacts.write_artifact("app-1", "note.txt", "hello")
    bin_path = artifacts.write_artifact("app-1", "shot.png", b"\x00\x01")
    assert text_path.read_text(encoding="utf-8") == "hello"
    assert bin_path.read_bytes() == b"\x00\x01"
    assert text_path.parent == bin_path.parent == tmp_path / "artifacts" / "app-1"


@pytest.mark.parametrize("bad_name", ["../x", "a/b", "a b", "..", "x\\y", ""])
def test_write_artifact_rejects_unsafe_names(bad_name: str) -> None:
    with pytest.raises(AutoJobApplyError):
        artifacts.write_artifact("app-1", bad_name, "data")


def test_snapshot_page_writes_png_and_html(tmp_path: Path) -> None:
    page = FakePage()
    paths = artifacts.snapshot_page("app-9", page, prefix="iter1")
    assert len(paths) == 2
    png, html = paths
    assert png.suffix == ".png" and png.read_bytes() == b"\x89PNG-fake-bytes"
    assert html.suffix == ".html" and "fake form" in html.read_text(encoding="utf-8")
    assert png.stem.startswith("iter1-") and html.stem.startswith("iter1-")
    assert png.parent == tmp_path / "artifacts" / "app-9"
    assert page.screenshot_calls == 1


def test_snapshot_page_honors_screenshots_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifacts, "_screenshots_enabled", lambda: False)
    page = FakePage()
    assert artifacts.snapshot_page("app-9", page) == []
    assert page.screenshot_calls == 0
    assert not (tmp_path / "artifacts").exists()


def test_snapshot_page_default_prefix() -> None:
    paths = artifacts.snapshot_page("app-2", FakePage())
    assert paths[0].stem.startswith("snapshot-")

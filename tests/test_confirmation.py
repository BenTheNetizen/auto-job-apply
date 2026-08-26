"""Tests for submission confirmation detection.

Covers: the ``SubmissionConfirmation`` enum + composition helper
(``services.confirmation.confirm_by``) per ATS plugin, and the filler.submit
wiring (REJECTED_* → failed + raised; CONFIRMED/UNKNOWN → submitted; verdict
recorded in status history; post-click non-retryability preserved).

All pages/plugins are fakes; no browser, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from auto_job_apply.errors import SubmissionError
from auto_job_apply.services import filler
from auto_job_apply.services.applications import (
    ApplicationsRow,
    StatusEvent,
    applications_store,
)
from auto_job_apply.services.ats import ashby, greenhouse, lever
from auto_job_apply.services.ats_registry import registry
from auto_job_apply.services.confirmation import (
    SubmissionConfirmation,
    confirm_by,
)


# --- fakes ---------------------------------------------------------------


class _Loc:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class ConfPage:
    """Minimal page fake: url property + content() + locator counting."""

    def __init__(
        self,
        *,
        url: str = "https://jobs.ashbyhq.com/acme/apply",
        content: str = "",
        present: tuple[str, ...] = (),
    ) -> None:
        self.url = url
        self._content = content
        self._present = set(present)

    def content(self) -> str:
        return self._content

    def locator(self, selector: str) -> _Loc:
        return _Loc(1 if selector in self._present else 0)

    def wait_for_load_state(self, state: str) -> None:  # pragma: no cover
        pass


def _fast_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse the poll window so UNKNOWN resolves instantly in tests."""
    monkeypatch.setattr("auto_job_apply.services.confirmation.MAX_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(
        "auto_job_apply.services.confirmation.POLL_INTERVAL_SECONDS", 0.0
    )


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    _fast_unknown(monkeypatch)


# --- enum + composition helper -------------------------------------------


class TestEnum:
    def test_values(self) -> None:
        assert [e.value for e in SubmissionConfirmation] == [
            "confirmed",
            "rejected_validation",
            "rejected_bot",
            "unknown",
        ]


class TestComposition:
    def test_redirect_wins(self) -> None:
        page = ConfPage(url="https://jobs.ashbyhq.com/acme/application-submitted")
        assert confirm_by(page, redirect_patterns=("/application-submitted",)) == (
            SubmissionConfirmation.CONFIRMED
        )

    def test_toast_selector_confirms(self) -> None:
        page = ConfPage(present=(".thank-you",))
        assert confirm_by(page, redirect_patterns=("/thanks",), toast_selectors=(".thank-you",)) == (
            SubmissionConfirmation.CONFIRMED
        )

    def test_generic_success_text_confirms(self) -> None:
        page = ConfPage(content="<html>Thank you! Your application was received.</html>")
        assert confirm_by(page, redirect_patterns=("/thanks",)) == (
            SubmissionConfirmation.CONFIRMED
        )

    def test_validation_selector_rejects(self) -> None:
        page = ConfPage(present=(".field-error", "div.error"))
        assert confirm_by(
            page,
            redirect_patterns=("/thanks",),
            validation_selectors=(".field-error",),
        ) == SubmissionConfirmation.REJECTED_VALIDATION

    def test_generic_error_text_rejects(self) -> None:
        page = ConfPage(content="<html>Submission failed: please correct the errors.</html>")
        assert confirm_by(page, redirect_patterns=("/thanks",)) == (
            SubmissionConfirmation.REJECTED_VALIDATION
        )

    def test_bot_iframe_rejects(self) -> None:
        page = ConfPage(present=('iframe[src*="captcha"]',))
        assert confirm_by(page, redirect_patterns=("/thanks",)) == (
            SubmissionConfirmation.REJECTED_BOT
        )

    def test_verify_human_text_rejects(self) -> None:
        page = ConfPage(content="<html>Please verify you are human</html>")
        assert confirm_by(page, redirect_patterns=("/thanks",)) == (
            SubmissionConfirmation.REJECTED_BOT
        )

    def test_no_signal_is_unknown(self) -> None:
        page = ConfPage(content="<html>plain page, no markers</html>")
        assert confirm_by(page, redirect_patterns=("/thanks",)) == (
            SubmissionConfirmation.UNKNOWN
        )


# --- per-ATS plugins ------------------------------------------------------


class TestAshbyPlugin:
    plugin = ashby.plugin

    def test_redirect_to_application_submitted(self) -> None:
        page = ConfPage(url="https://jobs.ashbyhq.com/acme/jobs/abc/application-submitted")
        assert self.plugin.confirm_submission(page) == SubmissionConfirmation.CONFIRMED

    def test_toast_style_inline_success(self) -> None:
        page = ConfPage(present=("[role=status]",))
        assert self.plugin.confirm_submission(page) == SubmissionConfirmation.CONFIRMED

    def test_error_list_rejects_validation(self) -> None:
        page = ConfPage(present=("[role=alert]",))
        assert self.plugin.confirm_submission(page) == (
            SubmissionConfirmation.REJECTED_VALIDATION
        )


class TestGreenhousePlugin:
    plugin = greenhouse.plugin

    def test_confirmation_view_url(self) -> None:
        page = ConfPage(url="https://boards.greenhouse.io/acme/jobs/1/confirmation")
        assert self.plugin.confirm_submission(page) == SubmissionConfirmation.CONFIRMED

    def test_toast_selector(self) -> None:
        page = ConfPage(present=("#application_confirmation",))
        assert self.plugin.confirm_submission(page) == SubmissionConfirmation.CONFIRMED

    def test_field_error_rejects(self) -> None:
        page = ConfPage(present=(".field-error",))
        assert self.plugin.confirm_submission(page) == (
            SubmissionConfirmation.REJECTED_VALIDATION
        )


class TestLeverPlugin:
    plugin = lever.plugin

    def test_thanks_redirect(self) -> None:
        page = ConfPage(url="https://jobs.lever.co/acme/abc/thanks")
        assert self.plugin.confirm_submission(page) == SubmissionConfirmation.CONFIRMED

    def test_thank_you_toast(self) -> None:
        page = ConfPage(present=(".thank-you",))
        assert self.plugin.confirm_submission(page) == SubmissionConfirmation.CONFIRMED

    def test_error_summary_rejects(self) -> None:
        page = ConfPage(present=("div.error",))
        assert self.plugin.confirm_submission(page) == (
            SubmissionConfirmation.REJECTED_VALIDATION
        )


class TestProtocol:
    def test_all_registry_plugins_implement_confirm_submission(self) -> None:
        assert registry(), "expected plugin singletons registered"
        for plugin in registry():
            assert callable(getattr(plugin, "confirm_submission", None))


# --- filler wiring ---------------------------------------------------------


class _FakeControl:
    def __init__(self) -> None:
        self.ops: list[tuple[str, Any]] = []

    def click(self) -> None:
        self.ops.append(("click", None))


class _FakeLocator:
    def __init__(self, control: _FakeControl | None) -> None:
        self._control = control

    def count(self) -> int:
        return 1 if self._control is not None else 0

    @property
    def first(self) -> "_FakeLocator":
        return self

    def click(self) -> None:
        self._control.click()

    def fill(self, value: str) -> None:
        pass


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://x/1"

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self._control)

    def get_by_label(self, label: str) -> _FakeLocator:  # fill ignores return
        return _FakeLocator(None)

    def get_by_role(self, role: str, name: str) -> _FakeLocator:
        return _FakeLocator(None)


class _FakePlugin:
    name = "ashby"

    def __init__(self, verdict: SubmissionConfirmation | Exception) -> None:
        self.submit_control = _FakeControl()
        self._verdict = verdict

    def pre_extract(self, page: Any) -> None:
        pass

    def post_fill(self, page: Any, answers: Any) -> None:
        pass

    def submit_button(self, page: Any) -> _FakeLocator:
        return _FakeLocator(self.submit_control)

    def confirm_submission(self, page: Any) -> SubmissionConfirmation:
        if isinstance(self._verdict, Exception):
            raise self._verdict
        return self._verdict


@pytest.fixture
def saved_row(tmp_path: Path) -> tuple[Path, ApplicationsRow]:
    csv = tmp_path / "apps.csv"
    row = ApplicationsRow(
        id="app-conf",
        job_url="https://x/1",
        ats_type="ashby",
        status="ready_to_submit",
        fields_json=[{"key": "k1", "label": "Full name", "type": "text", "required": True, "answer": "Taylor"}],
        status_history_json=[],
        created_at=datetime.now(UTC),
    )
    applications_store(csv).append(row)
    return csv, row


class TestFillerWiring:
    def _install(
        self,
        monkeypatch: pytest.MonkeyPatch,
        verdict: SubmissionConfirmation | Exception,
    ) -> _FakePlugin:
        plugin = _FakePlugin(verdict)
        monkeypatch.setattr(filler, "plugin_for", lambda url: plugin)
        monkeypatch.setattr(filler, "discover_fields", lambda page, pl: [])
        monkeypatch.setattr(filler.artifacts, "snapshot_page", lambda *a, **k: [])
        return plugin

    def test_confirmed_marks_submitted(
        self, monkeypatch: pytest.MonkeyPatch, saved_row: tuple[Path, ApplicationsRow]
    ) -> None:
        csv, row = saved_row
        self._install(monkeypatch, SubmissionConfirmation.CONFIRMED)
        page = _FakePage()
        updated = filler.submit(row.id, page_opener=lambda *a, **k: _open(page), applications_path=csv)
        assert updated.status == "submitted"
        assert updated.status_history_json[-1].raw_snippet == "confirmed"

    def test_unknown_still_submits_with_warning_logged(
        self, monkeypatch: pytest.MonkeyPatch, saved_row: tuple[Path, ApplicationsRow]
    ) -> None:
        csv, row = saved_row
        self._install(monkeypatch, SubmissionConfirmation.UNKNOWN)
        page = _FakePage()
        updated = filler.submit(
            row.id, page_opener=lambda *a, **k: _open(page), applications_path=csv
        )
        assert updated.status == "submitted"
        assert updated.status_history_json[-1].raw_snippet == "unknown"

    def test_rejected_validation_marks_failed_and_raises(
        self, monkeypatch: pytest.MonkeyPatch, saved_row: tuple[Path, ApplicationsRow]
    ) -> None:
        csv, row = saved_row
        self._install(monkeypatch, SubmissionConfirmation.REJECTED_VALIDATION)
        page = _FakePage()
        with pytest.raises(SubmissionError) as excinfo:
            filler.submit(row.id, page_opener=lambda *a, **k: _open(page), applications_path=csv)
        assert excinfo.value.context["confirmation"] == "rejected_validation"
        stored = applications_store(csv).get(row.id)
        assert stored.status == "failed"

    def test_rejected_bot_marks_failed_and_raises(
        self, monkeypatch: pytest.MonkeyPatch, saved_row: tuple[Path, ApplicationsRow]
    ) -> None:
        csv, row = saved_row
        self._install(monkeypatch, SubmissionConfirmation.REJECTED_BOT)
        page = _FakePage()
        with pytest.raises(SubmissionError) as excinfo:
            filler.submit(row.id, page_opener=lambda *a, **k: _open(page), applications_path=csv)
        assert excinfo.value.context["confirmation"] == "rejected_bot"
        stored = applications_store(csv).get(row.id)
        assert stored.status == "failed"

    def test_plugin_confirm_raises_is_treated_unknown(
        self, monkeypatch: pytest.MonkeyPatch, saved_row: tuple[Path, ApplicationsRow]
    ) -> None:
        csv, row = saved_row
        self._install(monkeypatch, RuntimeError("weird page"))
        page = _FakePage()
        updated = filler.submit(row.id, page_opener=lambda *a, **k: _open(page), applications_path=csv)
        assert updated.status == "submitted"

    def test_rejection_does_not_escalate_to_browserbase(
        self, monkeypatch: pytest.MonkeyPatch, saved_row: tuple[Path, ApplicationsRow]
    ) -> None:
        csv, row = saved_row
        self._install(monkeypatch, SubmissionConfirmation.REJECTED_VALIDATION)
        page = _FakePage()

        calls: list[str] = []

        def opener_factory(page_obj: Any):
            def factory(url: str, headless: bool, timeout: int):
                calls.append(url)
                return _open(page_obj)
            return factory

        monkeypatch.setenv("BROWSERBASE_API_KEY", "bb-key")
        with pytest.raises(SubmissionError):
            filler.submit(
                row.id,
                page_opener=opener_factory(page),
                browserbase_opener=opener_factory(page),
                applications_path=csv,
            )
        assert calls == ["https://x/1"], "browserbase escalation must not run post-click"


# helper context manager matching filler's page_opener shape
from contextlib import contextmanager


@contextmanager
def _open(page: Any):
    yield page

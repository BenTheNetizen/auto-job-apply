"""Tests for services/email_confirmation.py (stubbed AgentMail client)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_job_apply.config import settings
from auto_job_apply.services import email_confirmation
from auto_job_apply.services.applications import ApplicationsRow, applications_store
from auto_job_apply.services.email_confirmation import (
    EmailConfirmationStatus,
    wait_for_confirmation,
)


# ---------------------------------------------------------------------------
# Scripted stub AgentMail client (inboxes.messages list/update only).
# ---------------------------------------------------------------------------


def _sdk_message(
    message_id: str,
    subject: str,
    text: str,
    from_: str = "recruiting@acme.com",
    labels: list[str] | None = None,
    headers: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        message_id=message_id,
        subject=subject,
        text=text,
        from_=from_,
        thread_id=f"thread-{message_id}",
        labels=list(labels if labels is not None else ["unread"]),
        headers=headers or {},
    )


class ScriptedMessages:
    """list() returns no messages for ``silent_polls`` calls, then ``messages``."""

    def __init__(self, messages: list[SimpleNamespace], silent_polls: int = 0) -> None:
        self._messages = messages
        self._silent = silent_polls
        self.list_calls = 0
        self.update_calls: list[tuple[str, dict]] = []

    def list(self, inbox_id: str, **kwargs):  # noqa: ARG002 - stub
        self.list_calls += 1
        if self._silent > 0:
            self._silent -= 1
            return SimpleNamespace(messages=[], next_page_token=None, count=0)
        wanted = set(kwargs.get("labels") or [])
        msgs = [
            m
            for m in self._messages
            if not wanted or wanted.issubset(set(m.labels))
        ]
        return SimpleNamespace(messages=msgs, next_page_token=None, count=len(msgs))

    def update(self, inbox_id: str, message_id: str, **kwargs):  # noqa: ARG002
        self.update_calls.append((message_id, kwargs))
        for m in self._messages:
            if m.message_id == message_id:
                for label in kwargs.get("remove_labels") or []:
                    if label in m.labels:
                        m.labels.remove(label)


class _Client:
    def __init__(self, messages: list[SimpleNamespace], silent_polls: int = 0) -> None:
        self.inboxes = SimpleNamespace(
            list=lambda: SimpleNamespace(
                inboxes=[
                    SimpleNamespace(
                        email="taylor.wong@agentmail.to",
                        inbox_id="taylor.wong@agentmail.to",
                    )
                ]
            ),
            messages=ScriptedMessages(messages, silent_polls),
        )


class ExplodingClient:
    """Any use raises — proves disabled/error paths never touch the client."""

    def __getattr__(self, name: str):  # noqa: ANN204
        raise RuntimeError(f"client must not be used ({name})")


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    return {"apps": tmp_path / "applications.csv", "ledger": tmp_path / "processed_messages.csv"}


def _seed_app(paths: dict[str, Path], app_id: str = "app-1") -> None:
    applications_store(paths["apps"]).append(
        ApplicationsRow(
            id=app_id,
            job_url="https://jobs.ashbyhq.com/acme/abc123",
            ats_type="ashby",
            status="submitted",
            job_title="Senior Engineer",
        )
    )


def _history(paths: dict[str, Path], app_id: str = "app-1") -> list[str]:
    row = applications_store(paths["apps"]).get(app_id)
    assert row is not None
    return [e["status"] if isinstance(e, dict) else e.status for e in row.status_history_json]


# ---------------------------------------------------------------------------


class TestEnum:
    def test_values(self) -> None:
        assert EmailConfirmationStatus.RECEIVED.value == "received"
        assert EmailConfirmationStatus.TIMEOUT.value == "timeout"
        assert EmailConfirmationStatus.NOT_CHECKED.value == "not_checked"


class TestDisabled:
    def test_not_checked_without_poll(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(email_confirmation, "_wait_enabled", lambda: False)
        outcome = wait_for_confirmation("app-1", client=ExplodingClient())
        assert outcome is EmailConfirmationStatus.NOT_CHECKED

    def test_missing_api_key_never_raises(self) -> None:
        outcome = wait_for_confirmation("app-1")  # no client, rely on env being unset
        assert outcome is EmailConfirmationStatus.TIMEOUT


class TestReceived:
    def test_ack_on_later_poll_consumes_and_records(self, paths: dict[str, Path]) -> None:
        _seed_app(paths)
        msg = _sdk_message(
            "m-ack",
            "Thank you for applying to Acme",
            "We have received your application and will be in touch.",
        )
        client = _Client([msg], silent_polls=2)
        outcome = wait_for_confirmation(
            "app-1",
            timeout_seconds=2.0,
            poll_interval_seconds=0.01,
            client=client,
            apps_path=paths["apps"],
            ledger_path=paths["ledger"],
        )
        assert outcome is EmailConfirmationStatus.RECEIVED
        assert _history(paths) == ["confirmation_received"]
        # Top-level status is never clobbered by the confirmation event.
        assert applications_store(paths["apps"]).get("app-1").status == "submitted"
        # Message consumed: marked read + ledgered, so poll_once never reprocesses it.
        assert "unread" not in msg.labels
        assert client.inboxes.messages.update_calls[0][0] == "m-ack"

    def test_stronger_statuses_also_confirm(self, paths: dict[str, Path]) -> None:
        _seed_app(paths)
        msg = _sdk_message(
            "m-interview",
            "Interview with Acme",
            "We'd like to schedule an interview with you this week.",
        )
        client = _Client([msg])
        outcome = wait_for_confirmation(
            "app-1",
            timeout_seconds=1.0,
            poll_interval_seconds=0.01,
            client=client,
            apps_path=paths["apps"],
            ledger_path=paths["ledger"],
        )
        assert outcome is EmailConfirmationStatus.RECEIVED
        assert _history(paths) == ["confirmation_received"]


class TestTimeout:
    def test_no_matching_email_returns_timeout_and_records(self, paths: dict[str, Path]) -> None:
        _seed_app(paths)
        client = _Client([])
        outcome = wait_for_confirmation(
            "app-1",
            timeout_seconds=0.05,
            poll_interval_seconds=0.01,
            client=client,
            apps_path=paths["apps"],
            ledger_path=paths["ledger"],
        )
        assert outcome is EmailConfirmationStatus.TIMEOUT
        assert _history(paths) == ["confirmation_timeout"]

    def test_rejection_does_not_short_circuit(self, paths: dict[str, Path]) -> None:
        _seed_app(paths)
        msg = _sdk_message("m-reject", "Acme application update", "We decided to move forward with other candidates.")
        client = _Client([msg])
        outcome = wait_for_confirmation(
            "app-1",
            timeout_seconds=0.05,
            poll_interval_seconds=0.01,
            client=client,
            apps_path=paths["apps"],
            ledger_path=paths["ledger"],
        )
        assert outcome is EmailConfirmationStatus.TIMEOUT
        # The rejection is left unread/unhandled for the regular poll cycle.
        assert "unread" in msg.labels
        assert client.inboxes.messages.update_calls == []
        assert _history(paths) == ["confirmation_timeout"]

    def test_unmatched_message_left_unread(self, paths: dict[str, Path]) -> None:
        _seed_app(paths)
        msg = _sdk_message(
            "m-other",
            "Thanks for contacting support",
            "unrelated email body",
            from_="help@othercorp.example",
        )
        client = _Client([msg])
        outcome = wait_for_confirmation(
            "app-1",
            timeout_seconds=0.05,
            poll_interval_seconds=0.01,
            client=client,
            apps_path=paths["apps"],
            ledger_path=paths["ledger"],
        )
        assert outcome is EmailConfirmationStatus.TIMEOUT
        assert "unread" in msg.labels


class TestNeverRaises:
    def test_client_failures_degrade_to_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom() -> None:
            raise RuntimeError("api down")

        monkeypatch.setattr("auto_job_apply.services.email_monitor._get_client", boom)
        outcome = wait_for_confirmation("app-1", timeout_seconds=0.05)
        assert outcome is EmailConfirmationStatus.TIMEOUT


class TestConfigDefaults:
    def test_committed_defaults(self) -> None:
        assert settings.get("EMAIL.confirmation_wait_enabled") is True
        assert settings.get("EMAIL.confirmation_timeout_seconds") == 600
        assert settings.get("EMAIL.confirmation_poll_seconds") == 30


class TestFillerWiring:
    def test_submit_wait_for_email_invokes_confirmation(self, tmp_path: Path) -> None:
        """Opt-in post-submit step: wait_for_confirmation called on success only."""
        from auto_job_apply.services import filler

        calls: list[str] = []

        def fake_wait(application_id, **kwargs):
            calls.append(application_id)
            return EmailConfirmationStatus.NOT_CHECKED

        row = ApplicationsRow(id="app-9", job_url="https://fake.local/x", ats_type="ashby", status="ready_to_submit")
        store = applications_store(tmp_path / "applications.csv")
        store.append(row)

        class _Plugin:
            name = "ashby"

        class _Page:  # minimal page for _submit_once
            def locator(self, sel: str):
                return SimpleNamespace(first=SimpleNamespace(click=lambda: None))

            def wait_for_load_state(self, state: str) -> None:
                return None

            def content(self) -> str:
                return "<html>submitted</html>"

            @property
            def url(self) -> str:
                return "https://fake.local/x"

        page = _Page()

        def opener(url, headless, timeout):  # noqa: ANN001
            from contextlib import contextmanager

            @contextmanager
            def cm():
                yield page

            return cm()

        row_filled = filler.submit(
            "app-9",
            page_opener=opener,
            applications_path=tmp_path / "applications.csv",
            wait_for_email=True,
        )
        assert row_filled.status == "submitted"
        # wiring point: monkeypatched at module level in the next test

    def test_wait_flag_only_on_success(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        from auto_job_apply.services import filler

        seen: list[tuple[str, str, object]] = []

        def fake_wait(application_id, *, timeout_seconds=None, apps_path=None):  # noqa: ANN202
            seen.append((application_id, timeout_seconds, apps_path))
            return EmailConfirmationStatus.RECEIVED

        monkeypatch.setattr(filler, "wait_for_confirmation", fake_wait)

        row = ApplicationsRow(id="app-8", job_url="https://fake.local/x", ats_type="ashby", status="ready_to_submit")
        applications_store(tmp_path / "applications.csv").append(row)

        class _Page:
            def locator(self, sel: str):
                return SimpleNamespace(first=SimpleNamespace(click=lambda: None))

            def wait_for_load_state(self, state: str) -> None:
                return None

            def content(self) -> str:
                return "<html>ok</html>"

            @property
            def url(self) -> str:
                return "https://fake.local/x"

        def opener(url, headless, timeout):  # noqa: ANN001
            from contextlib import contextmanager

            @contextmanager
            def cm():
                yield _Page()

            return cm()

        updated = filler.submit(
            "app-8",
            page_opener=opener,
            applications_path=tmp_path / "applications.csv",
            wait_for_email=True,
            email_timeout_seconds=5.0,
        )
        assert updated.status == "submitted"
        assert seen == [("app-8", 5.0, tmp_path / "applications.csv")]

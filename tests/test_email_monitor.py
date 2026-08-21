"""Tests for services/email_monitor.py with a stubbed AgentMail client."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from auto_job_apply.services import email_monitor, replay_ledger
from auto_job_apply.services.applications import (
    ApplicationsRow,
    StatusEvent,
    append_status,
    applications_store,
)
from auto_job_apply.services.email_monitor import (
    IncomingMessage,
    handle_message,
    match_application,
    normalize_sdk_message,
    poll_once,
)


# ---------------------------------------------------------------------------
# Stub AgentMail client (inboxes.messages.list/update only).
# ---------------------------------------------------------------------------


class FakeMessages:
    def __init__(self, messages: list[SimpleNamespace]) -> None:
        self._messages = messages
        self.update_calls: list[tuple[str, dict]] = []

    def list(self, inbox_id: str, **kwargs):  # noqa: ARG002 - stub
        wanted = set(kwargs.get("labels") or [])
        msgs = [
            m
            for m in self._messages
            if not wanted or wanted.issubset(set(m.labels))
        ]
        return SimpleNamespace(
            messages=msgs, next_page_token=None, count=len(msgs)
        )

    def update(self, inbox_id: str, message_id: str, **kwargs):  # noqa: ARG002
        self.update_calls.append((message_id, kwargs))
        for m in self._messages:
            if m.message_id == message_id:
                for label in kwargs.get("remove_labels") or []:
                    if label in m.labels:
                        m.labels.remove(label)


class FakeInboxes:
    def __init__(self, messages: list[SimpleNamespace], email: str = "taylor.wong@agentmail.to") -> None:
        self.messages = FakeMessages(messages)
        self._email = email

    def list(self):
        return SimpleNamespace(
            inboxes=[SimpleNamespace(email=self._email, inbox_id=self._email)]
        )


class FakeClient:
    def __init__(self, messages: list[SimpleNamespace]) -> None:
        self.inboxes = FakeInboxes(messages)


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


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "apps": tmp_path / "applications.csv",
        "ledger": tmp_path / "processed_messages.csv",
    }


def _seed_app(
    apps_path: Path,
    app_id: str = "app-1",
    job_url: str = "https://jobs.ashbyhq.com/acme/abc123",
    job_title: str = "Senior Engineer",
) -> None:
    applications_store(apps_path).append(
        ApplicationsRow(
            id=app_id,
            job_url=job_url,
            ats_type="ashby",
            status="submitted",
            job_title=job_title,
        )
    )


class TestMatching:
    def test_explicit_header_match(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"], app_id="app-42")
        msg = IncomingMessage(
            message_id="m1",
            subject="no hints here",
            headers={"x-application-id": "app-42"},
        )
        row = match_application(msg, paths["apps"])
        assert row is not None and row.id == "app-42"

    def test_subject_token_match(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"], app_id="app-7")
        msg = IncomingMessage(
            message_id="m2", subject="Re: your application [app:app-7]"
        )
        row = match_application(msg, paths["apps"])
        assert row is not None and row.id == "app-7"

    def test_sender_domain_org_match(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"], job_url="https://jobs.lever.co/acme/xyz")
        msg = IncomingMessage(
            message_id="m3", subject="hello", from_address="jane@acme.com"
        )
        assert match_application(msg, paths["apps"]) is not None

    def test_subject_org_match(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"], job_url="https://boards.greenhouse.io/acme/jobs/1")
        msg = IncomingMessage(
            message_id="m4",
            subject="Acme - next steps",
            from_address="noreply@greenhouse-mail.io",
        )
        assert match_application(msg, paths["apps"]) is not None

    def test_job_title_substring_match(self, paths: dict[str, Path]) -> None:
        _seed_app(
            paths["apps"],
            job_url="https://example.com/apply/123",  # no org slug hint
            job_title="Senior Engineer",
        )
        msg = IncomingMessage(
            message_id="m5",
            subject="Your senior engineer application",
            from_address="someone@unknown.io",
        )
        assert match_application(msg, paths["apps"]) is not None

    def test_no_match_returns_none(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"])
        msg = IncomingMessage(
            message_id="m6",
            subject="unrelated newsletter",
            from_address="spam@elsewhere.net",
        )
        assert match_application(msg, paths["apps"]) is None


class TestHandleMessage:
    def test_full_pipeline(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"])
        sdk_msg = _sdk_message(
            "m1",
            "Update on your application",
            "Unfortunately, we have decided to move forward with other candidates.",
        )
        client = FakeClient([sdk_msg])
        result = handle_message(
            normalize_sdk_message(sdk_msg),
            client=client,
            inbox_id="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        assert result.outcome == "updated"
        assert result.application_id == "app-1"
        assert result.status == "rejected"

        row = applications_store(paths["apps"]).get("app-1")
        assert row is not None
        assert row.status == "rejected"
        assert len(row.status_history_json) == 1
        event = row.status_history_json[0]
        assert isinstance(event, StatusEvent)
        assert event.source == "email"
        assert "unfortunately" in event.raw_snippet.lower()

        assert replay_ledger.is_processed("m1", paths["ledger"])
        assert client.inboxes.messages.update_calls == [
            ("m1", {"remove_labels": ["unread"]})
        ]

    def test_duplicate_short_circuits_and_cleans_up_read(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"])
        replay_ledger.record("m1", "app-1", "rejected", paths["ledger"])
        sdk_msg = _sdk_message("m1", "anything", "unfortunately no")
        client = FakeClient([sdk_msg])
        result = handle_message(
            normalize_sdk_message(sdk_msg),
            client=client,
            inbox_id="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        assert result.outcome == "duplicate"
        row = applications_store(paths["apps"]).get("app-1")
        assert row is not None and row.status_history_json == []
        assert client.inboxes.messages.update_calls == [
            ("m1", {"remove_labels": ["unread"]})
        ]

    def test_unmatched_left_unread_and_warns(
        self, paths: dict[str, Path], caplog: pytest.LogCaptureFixture
    ) -> None:
        _seed_app(paths["apps"])
        sdk_msg = _sdk_message(
            "m9", "totally unrelated", "hello there", from_="x@nomatch.io"
        )
        client = FakeClient([sdk_msg])
        with caplog.at_level("WARNING", logger="auto_job_apply.email_monitor"):
            result = handle_message(
                normalize_sdk_message(sdk_msg),
                client=client,
                inbox_id="taylor.wong@agentmail.to",
                ledger_path=paths["ledger"],
                apps_path=paths["apps"],
            )
        assert result.outcome == "unmatched"
        assert client.inboxes.messages.update_calls == []  # not marked read
        assert "unread" in sdk_msg.labels
        assert "unmatched message m9" in caplog.text
        assert replay_ledger.is_processed("m9", paths["ledger"]) is False


class TestPollOnce:
    def test_one_unseen_message_updates_one_row_then_not_repulled(
        self, paths: dict[str, Path]
    ) -> None:
        _seed_app(paths["apps"])
        sdk_msg = _sdk_message(
            "m1",
            "Thank you for applying",
            "Thank you for applying. We have received your application.",
        )
        client = FakeClient([sdk_msg])
        kwargs = dict(
            client=client,
            account="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        first = poll_once(**kwargs)
        assert first.polled == 1 and first.updated == 1
        assert first.results[0].status == "acknowledged"

        row = applications_store(paths["apps"]).get("app-1")
        assert row is not None
        assert row.status == "acknowledged"
        assert len(row.status_history_json) == 1

        # Message was marked read -> not returned on next poll.
        second = poll_once(**kwargs)
        assert second.polled == 0

    def test_one_bad_message_does_not_kill_loop(
        self, paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Hermetic: the ambiguous message must hit a *failing* classifier
        # regardless of whether the shell env has a live OPENROUTER_API_KEY.
        from auto_job_apply.services import status_parser

        monkeypatch.setattr(
            status_parser,
            "_llm_classify",
            lambda s, b: status_parser.ParsedStatus(
                status=status_parser.ApplicationStatus.unknown,
                confidence=0.0,
                raw_snippet="",
            ),
        )
        _seed_app(paths["apps"], app_id="app-good")
        bad = _sdk_message(
            "bad-1", "Acme ambiguous", "no rules match this body at all"
        )
        good = _sdk_message(
            "good-1",
            "Interview invitation",
            "We'd like to invite you to interview with the team.",
        )
        client = FakeClient([bad, good])
        summary = poll_once(
            client=client,
            account="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        # bad-1: matches app by sender domain (acme.com), classification
        # fails (no LLM key in tests) -> error, loop continues to good-1.
        assert summary.polled == 2
        assert summary.errors == 1
        assert summary.updated == 1
        by_id = {r.message_id: r for r in summary.results}
        assert by_id["bad-1"].outcome == "error"
        assert by_id["good-1"].status == "interview_scheduled"

    def test_unmatched_recycled_next_interval(self, paths: dict[str, Path]) -> None:
        _seed_app(paths["apps"])
        unmatched = _sdk_message(
            "u1", "random promo", "buy things", from_="deals@shop.io"
        )
        client = FakeClient([unmatched])
        kwargs = dict(
            client=client,
            account="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        first = poll_once(**kwargs)
        assert first.unmatched == 1
        assert client.inboxes.messages.update_calls == []
        second = poll_once(**kwargs)
        assert second.polled == 1 and second.unmatched == 1  # still unread


class TestAppendStatusHelper:
    def test_append_status_updates_top_level_and_history(self, tmp_path: Path) -> None:
        apps = tmp_path / "applications.csv"
        _seed_app(apps)
        ok = append_status(
            "app-1",
            StatusEvent(
                status="offer",
                source="email",
                raw_snippet="pleased to extend",
                at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            ),
            path=apps,
        )
        assert ok is True
        row = applications_store(apps).get("app-1")
        assert row is not None and row.status == "offer"
        assert [e.status for e in row.status_history_json] == ["offer"]

    def test_append_status_missing_row(self, tmp_path: Path) -> None:
        ok = append_status(
            "nope",
            StatusEvent(
                status="offer",
                source="email",
                at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            ),
            path=tmp_path / "applications.csv",
        )
        assert ok is False

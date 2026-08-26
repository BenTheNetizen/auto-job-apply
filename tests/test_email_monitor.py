"""Tests for services/email_monitor.py with a stubbed AgentMail client."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

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


@pytest.fixture(autouse=True)
def fake_llm_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Hermetic LLM match tier for every test: default = no match, no network.

    email_monitor imports services.llm lazily at call time, so patching
    sys.modules intercepts it. Per-test overrides set
    ``fake.structured.return_value.invoke.return_value`` / ``side_effect``.
    """
    import sys

    fake = ModuleType("auto_job_apply.services.llm")
    runnable = MagicMock()
    runnable.invoke.return_value = SimpleNamespace(
        application_id=None, match_confidence=0.0
    )
    fake.structured = MagicMock(return_value=runnable)  # type: ignore[attr-defined]
    fake.get_llm = MagicMock(return_value=object())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "auto_job_apply.services.llm", fake)
    return fake


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


class TestLlmMatch:
    """Tier 4: cheap LLM match when deterministic rules miss."""

    def _rule_missing_msg(self) -> IncomingMessage:
        # org slug 'acme' absent from sender/subject; title absent from subject.
        return IncomingMessage(
            message_id="mx",
            subject="interview availability this week",
            text="Can you do Thursday at 2pm?",
            from_address="someone@unknown.io",
        )

    def _set_llm_result(
        self, fake_llm_module: ModuleType, application_id, confidence
    ) -> None:
        fake_llm_module.structured.return_value.invoke.return_value = (
            SimpleNamespace(
                application_id=application_id, match_confidence=confidence
            )
        )

    def test_llm_match_applied_above_threshold(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"], app_id="app-9")
        self._set_llm_result(fake_llm_module, "app-9", 0.9)
        row = match_application(self._rule_missing_msg(), paths["apps"])
        assert row is not None and row.id == "app-9"
        fake_llm_module.get_llm.assert_called_once_with(role="match")

    def test_llm_match_at_threshold_not_applied(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"], app_id="app-9")
        self._set_llm_result(fake_llm_module, "app-9", 0.6)
        assert match_application(self._rule_missing_msg(), paths["apps"]) is None

    def test_llm_match_below_threshold_not_applied(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"], app_id="app-9")
        self._set_llm_result(fake_llm_module, "app-9", 0.4)
        assert match_application(self._rule_missing_msg(), paths["apps"]) is None

    def test_llm_match_null_id_not_applied(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"], app_id="app-9")
        self._set_llm_result(fake_llm_module, None, 0.95)
        assert match_application(self._rule_missing_msg(), paths["apps"]) is None

    def test_llm_match_unknown_id_ignored(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"], app_id="app-9")
        self._set_llm_result(fake_llm_module, "ghost-app", 0.99)
        assert match_application(self._rule_missing_msg(), paths["apps"]) is None

    def test_llm_failure_degrades_to_unmatched(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"], app_id="app-9")
        fake_llm_module.structured.return_value.invoke.side_effect = RuntimeError(
            "openrouter down"
        )
        assert match_application(self._rule_missing_msg(), paths["apps"]) is None

    def test_rules_short_circuit_llm(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"], job_url="https://jobs.lever.co/acme/xyz")
        msg = IncomingMessage(
            message_id="mx", subject="hello", from_address="jane@acme.com"
        )
        assert match_application(msg, paths["apps"]) is not None
        fake_llm_module.structured.assert_not_called()

    def test_handle_message_llm_match_pipeline(
        self, paths: dict[str, Path], fake_llm_module: ModuleType
    ) -> None:
        _seed_app(paths["apps"])
        self._set_llm_result(fake_llm_module, "app-1", 0.85)
        sdk_msg = _sdk_message(
            "mllm",
            "interview availability this week",
            "Unfortunately, we have decided to move forward with other candidates.",
            from_="someone@unknown.io",
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
        assert replay_ledger.is_processed("mllm", paths["ledger"])
        assert client.inboxes.messages.update_calls == [
            ("mllm", {"remove_labels": ["unread"]})
        ]


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

    def test_append_status_history_only_keeps_top_level(
        self, tmp_path: Path
    ) -> None:
        apps = tmp_path / "applications.csv"
        _seed_app(apps)
        ok = append_status(
            "app-1",
            StatusEvent(
                status="unknown",
                source="email",
                raw_snippet="ambiguous",
                at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
            ),
            path=apps,
            update_top_level=False,
        )
        assert ok is True
        row = applications_store(apps).get("app-1")
        assert row is not None and row.status == "submitted"  # untouched
        assert [e.status for e in row.status_history_json] == ["unknown"]

    def test_append_status_history_is_atomic_across_threads(
        self, tmp_path: Path
    ) -> None:
        """Concurrent appends must not lose history events (lost-update race)."""
        import threading

        apps = tmp_path / "applications.csv"
        _seed_app(apps)
        per_thread = 25

        def writer(tag: str) -> None:
            for i in range(per_thread):
                assert append_status(
                    "app-1",
                    StatusEvent(
                        status=f"{tag}-{i}",
                        source="email",
                        at=__import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc
                        ),
                    ),
                    path=apps,
                )

        threads = [
            threading.Thread(target=writer, args=(f"w{n}",)) for n in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        row = applications_store(apps).get("app-1")
        assert row is not None
        assert len(row.status_history_json) == 2 * per_thread


class TestUnknownStatusKeepsRow:
    """LLM 'unknown' (confidence>0) appends history but preserves status."""

    def test_unknown_appends_history_without_status_overwrite(
        self, paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from auto_job_apply.services import status_parser

        monkeypatch.setattr(
            email_monitor,
            "parse",
            lambda s, b: status_parser.ParsedStatus(
                status=status_parser.ApplicationStatus.unknown,
                confidence=0.7,
                raw_snippet="ambiguous snippet",
            ),
        )
        _seed_app(paths["apps"])
        msg = IncomingMessage(
            message_id="amb-1",
            subject="quick update",
            text="something vague",
            from_address="jane@acme.com",
        )
        client = FakeClient([])
        result = handle_message(
            msg,
            client=client,
            inbox_id="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        assert result.outcome == "updated"
        row = applications_store(paths["apps"]).get("app-1")
        assert row is not None
        assert row.status == "submitted"  # NOT clobbered by 'unknown'
        assert [e.status for e in row.status_history_json] == ["unknown"]


class TestPreSubmitStatusNotWedged:
    """Email classifications must never overwrite a pre-submit pipeline state
    (needs_review / ready_to_submit / in_progress) — the review gate keys on
    top-level status, so history-only append keeps submission unblocked."""

    def test_email_on_ready_to_submit_row_goes_to_history_only(
        self, paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from auto_job_apply.services import status_parser

        _seed_app(paths["apps"])
        # Flip the seeded row into a pre-submit pipeline state.
        row = applications_store(paths["apps"]).get("app-1")
        assert row is not None
        applications_store(paths["apps"]).update(
            "app-1", row.model_copy(update={"status": "ready_to_submit"})
        )

        monkeypatch.setattr(
            email_monitor,
            "parse",
            lambda s, b: status_parser.ParsedStatus(
                status=status_parser.ApplicationStatus.acknowledged,
                confidence=0.9,
                raw_snippet="thanks for applying",
            ),
        )
        msg = IncomingMessage(
            message_id="pre-1",
            subject="Application received",
            text="Thanks for applying, we'll be in touch.",
            from_address="noreply@ashbyhq.com",
            headers={"x-application-id": "app-1"},
        )
        client = FakeClient([])
        result = handle_message(
            msg,
            client=client,
            inbox_id="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        assert result.outcome == "updated"
        row2 = applications_store(paths["apps"]).get("app-1")
        assert row2 is not None
        assert row2.status == "ready_to_submit"  # gate unwedged
        assert row2.status_history_json[-1].status == "acknowledged"

    def test_email_on_post_submit_row_still_updates_top_level(
        self, paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pipeline states past submission (submitted/failed/on_hold) remain
        # fully managed by email statuses.
        from auto_job_apply.services import status_parser

        _seed_app(paths["apps"])  # status="submitted"
        monkeypatch.setattr(
            email_monitor,
            "parse",
            lambda s, b: status_parser.ParsedStatus(
                status=status_parser.ApplicationStatus.rejected,
                confidence=0.9,
                raw_snippet="decided to move forward with other candidates",
            ),
        )
        msg = IncomingMessage(
            message_id="post-1",
            subject="Application update",
            text="Unfortunately, we have decided to move forward with other candidates.",
            from_address="noreply@ashbyhq.com",
            headers={"x-application-id": "app-1"},
        )
        client = FakeClient([])
        result = handle_message(
            msg,
            client=client,
            inbox_id="taylor.wong@agentmail.to",
            ledger_path=paths["ledger"],
            apps_path=paths["apps"],
        )
        assert result.outcome == "updated"
        row = applications_store(paths["apps"]).get("app-1")
        assert row is not None
        assert row.status == "rejected"

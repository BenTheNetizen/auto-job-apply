"""Spec: .spec/AutoJobApply/shared-infra/langfuse-tracing.md

Acceptance:
- env absent → factories no-op (None) and log once
- env present → Langfuse client with the right base URL, and a
  LangChain-compatible CallbackHandler
- score_eval posts through to the client's score API and returns True;
  no-client → False; post failure → False
- flush() delegates to the client when one exists
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from auto_job_apply.services import langfuse_service as svc


@pytest.fixture(autouse=True)
def reset_between_tests():
    svc.reset()
    yield
    svc.reset()


class TestEnvAbsent:
    def test_client_none_without_keys(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
        assert svc.get_client() is None

    def test_handler_none_without_keys(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        assert svc.get_callback_handler() is None

    def test_score_eval_false_without_client(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        assert svc.score_eval("run", "item", "metric", 1.0) is False

    def test_missing_env_logs_once(self, monkeypatch, caplog):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        with caplog.at_level("INFO", logger="auto_job_apply.langfuse"):
            svc.get_client()  # first call: logs
            svc.get_client()  # second call: silent
        msgs = [r.message for r in caplog.records if "disabled" in r.message]
        assert len(msgs) == 1


class TestEnvPresent:
    def test_client_constructed_with_base_url(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.langfuse.test")

        fake_instance = MagicMock(name="LangfuseInstance")
        with patch("langfuse.Langfuse", return_value=fake_instance) as ctor:
            client = svc.get_client()

        assert client is fake_instance
        ctor.assert_called_once_with(host="https://example.langfuse.test")

    def test_client_host_kwarg_absent_without_url(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

        with patch("langfuse.Langfuse", return_value=MagicMock()) as ctor:
            svc.get_client()

        ctor.assert_called_once_with()

    def test_langfuse_host_env_alias_supported(self, monkeypatch):
        # Some setups (Langfuse self-host docs) call it LANGFUSE_HOST.
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_HOST", "https://self-host.example")
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

        with patch("langfuse.Langfuse", return_value=MagicMock()) as ctor:
            svc.get_client()

        ctor.assert_called_once_with(host="https://self-host.example")

    def test_single_key_absent_disables_client(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")  # no secret key
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        assert svc.get_client() is None


class TestCallbackHandler:
    def test_handler_uses_public_key_env(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

        with (
            patch("langfuse.Langfuse", return_value=MagicMock()),
            patch("langfuse.langchain.CallbackHandler") as handler_ctor,
        ):
            handler_ctor.return_value = MagicMock()
            handler = svc.get_callback_handler()

        assert handler is handler_ctor.return_value
        handler_ctor.assert_called_once_with(public_key="pk-test")

    def test_handler_cached_across_calls(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        with (
            patch("langfuse.Langfuse", return_value=MagicMock()),
            patch("langfuse.langchain.CallbackHandler", return_value=MagicMock()) as ctor,
        ):
            first = svc.get_callback_handler()
            second = svc.get_callback_handler()
        assert first is second
        assert ctor.call_count == 1


class TestScoreEval:
    def test_posts_fields_and_returns_true(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(svc, "get_client", lambda: fake_client)
        ok = svc.score_eval("run-x", "trace-123", "required_completion", 1.0, "note")
        assert ok is True
        fake_client.api.scores.create.assert_called_once_with(
            name="required_completion",
            value=1.0,
            trace_id="trace-123",
            comment="note",
        )

    def test_empty_comment_posts_as_none(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(svc, "get_client", lambda: fake_client)
        svc.score_eval("run-x", "trace-123", "required_completion", 1.0)
        kwargs = fake_client.api.scores.create.call_args.kwargs
        assert kwargs["comment"] is None

    def test_returns_false_on_post_failure(self, monkeypatch):
        fake_client = MagicMock()
        fake_client.api.scores.create.side_effect = RuntimeError("boom")
        monkeypatch.setattr(svc, "get_client", lambda: fake_client)
        ok = svc.score_eval("run-x", "trace-123", "required_completion", 1.0)
        assert ok is False


class TestFlush:
    def test_flush_noop_without_client(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        svc.flush()  # must not raise

    def test_flush_delegates(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(svc, "get_client", lambda: fake_client)
        svc.reset()  # clear memoized client so monkeypatch lands
        # re-internalize the fake
        svc._client = fake_client  # noqa: SLF001
        svc.flush()
        fake_client.flush.assert_called_once()

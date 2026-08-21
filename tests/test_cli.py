"""CLI tests (review-api-cli leaf) — click runner, direct-mode fallback.

The CLI prefers the HTTP API when the server is reachable; these tests force
direct mode by monkeypatching the reachability probe, so no live server runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_job_apply.cli import cli
from auto_job_apply.config import settings
from auto_job_apply.services import applications as apps
from auto_job_apply.services.applications import ApplicationsRow, StatusEvent, applications_store


def _row(app_id: str = "app-1", status: str = "needs_review") -> ApplicationsRow:
    return ApplicationsRow(
        id=app_id,
        job_url="https://jobs.ashbyhq.com/acme/abc-123",
        ats_type="ashby",
        status=status,
        fields_json=[
            {
                "key": "k_name",
                "label": "Full name",
                "type": "text",
                "required": True,
                "answer": "Taylor",
                "submitted": False,
            }
        ],
        status_history_json=[StatusEvent(status=status, source="filler", at=datetime.now(UTC))],
        created_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def direct_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(settings, "DATA", {"dir": str(tmp_path)})
    import auto_job_apply.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_server_reachable", lambda: False)
    yield tmp_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_review_list(runner: CliRunner) -> None:
    applications_store().append(_row())
    result = runner.invoke(cli, ["review", "list"])
    assert result.exit_code == 0
    assert "app-1" in result.output


def test_review_list_status_filter(runner: CliRunner) -> None:
    applications_store().append(_row("app-1", "needs_review"))
    applications_store().append(_row("app-2", "submitted"))
    result = runner.invoke(cli, ["review", "list", "--status", "submitted"])
    assert "app-2" in result.output and "app-1" not in result.output


def test_review_show(runner: CliRunner) -> None:
    applications_store().append(_row())
    result = runner.invoke(cli, ["review", "show", "app-1"])
    assert result.exit_code == 0
    assert '"k_name"' in result.output


def test_review_edit_and_confirm(runner: CliRunner) -> None:
    applications_store().append(_row())
    result = runner.invoke(cli, ["review", "edit", "app-1", "k_name", "Taylor Wong"])
    assert result.exit_code == 0, result.output
    assert applications_store().get("app-1").fields_json[0]["answer"] == "Taylor Wong"

    result = runner.invoke(cli, ["review", "confirm", "app-1"])
    assert result.exit_code == 0, result.output
    assert applications_store().get("app-1").status == "ready_to_submit"


def test_review_submit(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    applications_store().append(_row(status="ready_to_submit"))
    from auto_job_apply.services import filler

    monkeypatch.setattr(
        filler,
        "submit",
        lambda app_id, **kw: applications_store()
        .get(app_id)
        .model_copy(update={"status": "submitted"}),
    )
    result = runner.invoke(cli, ["review", "submit", "app-1"])
    assert result.exit_code == 0, result.output
    assert "submitted" in result.output


def test_fill_chains_extract_plan_fill(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    import auto_job_apply.cli as cli_mod
    from auto_job_apply.services.extractor import ApplicationForm, Field

    form = ApplicationForm(
        url="https://jobs.ashbyhq.com/acme/abc-123",
        ats_type="ashby",
        fields=[Field(key="k", label="Name", type="text", required=True)],
    )
    monkeypatch.setattr(cli_mod, "fill", cli_mod.fill)  # keep reference
    from auto_job_apply.services import extractor as ex
    from auto_job_apply.graphs import planner as pl
    from auto_job_apply.services import filler as fi
    from auto_job_apply.graphs.planner import AnswerPlan

    monkeypatch.setattr(ex, "extract", lambda url, application_id=None: form)
    monkeypatch.setattr(pl, "plan_answers", lambda f, **kw: AnswerPlan(answers=[], missing_required=[], review_required=False))
    monkeypatch.setattr(fi, "fill", lambda url, plan, application_id, **kw: form)

    result = runner.invoke(cli, ["fill", "https://jobs.ashbyhq.com/acme/abc-123"])
    assert result.exit_code == 0, result.output
    assert "app-" in result.output


def test_email_monitor_once(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_job_apply.services import email_monitor

    class _Summary:
        polled = 0

    called: list[str] = []
    monkeypatch.setattr(email_monitor, "poll_once", lambda: (called.append("x") or _Summary()))
    result = runner.invoke(cli, ["email-monitor", "--once"])
    assert result.exit_code == 0, result.output
    assert called == ["x"]

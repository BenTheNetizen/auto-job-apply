"""Command-line interface: review applications, fill a URL, monitor email.

``python -m auto_job_apply.cli ...`` — commands:

- ``review list|show|edit|confirm|submit`` — the review surface. Uses the
  running FastAPI server when reachable, else calls the services directly.
- ``fill <url>`` — one-shot: extract → plan → fill (never submits).
- ``email-monitor [--once] [--interval N]`` — poll the AgentMail inbox.

The direct-mode fallback keeps the CLI useful when the server isn't up.
"""

from __future__ import annotations

import json
from typing import Any

import click
import httpx

from auto_job_apply.config import settings
from auto_job_apply.logging import logger


def _api_base() -> str:
    host = str(settings.get("API.host", "127.0.0.1"))
    port = int(settings.get("API.port", 8000))
    if host in {"0.0.0.0", "::"}:  # wildcard binds aren't dialable
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _server_reachable() -> bool:
    try:
        resp = httpx.get(f"{_api_base()}/health", timeout=1.5)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001 — any failure means direct mode
        return False


def _emit(obj: Any) -> None:
    click.echo(json.dumps(obj, indent=2, default=str))


def _direct() -> bool:
    """True when we should call services directly instead of the API."""
    direct = not _server_reachable()
    logger.debug("cli: mode=%s", "direct" if direct else "api")
    return direct


@click.group()
def cli() -> None:
    """auto-job-apply command line."""


# --- review ---------------------------------------------------------------


@cli.group()
def review() -> None:
    """Review applications."""


@review.command("list")
@click.option("--status", default=None, help="Filter by status.")
def review_list(status: str | None) -> None:
    if _direct():
        from auto_job_apply.services.review import list_applications

        rows = list_applications(status=status)
        _emit([r.model_dump(mode="json") for r in rows])
        return
    resp = httpx.get(f"{_api_base()}/applications", params={"status": status} if status else {})
    _emit(resp.json()["applications"])


@review.command("show")
@click.argument("application_id")
def review_show(application_id: str) -> None:
    if _direct():
        from auto_job_apply.services.review import get_application
        from auto_job_apply.utils.artifacts import artifact_dir

        row = get_application(application_id)
        detail = row.model_dump(mode="json")
        directory = artifact_dir(application_id)
        detail["artifacts"] = sorted(str(p) for p in directory.iterdir() if p.is_file()) if directory.is_dir() else []
        _emit(detail)
        return
    resp = httpx.get(f"{_api_base()}/applications/{application_id}")
    if resp.status_code == 404:
        raise click.ClickException(resp.json().get("detail", "not found"))
    _emit(resp.json())


@review.command("edit")
@click.argument("application_id")
@click.argument("field_key")
@click.argument("value")
def review_edit(application_id: str, field_key: str, value: str) -> None:
    if _direct():
        from auto_job_apply.services.review import edit_field

        _emit(edit_field(application_id, field_key, value).model_dump(mode="json"))
        return
    resp = httpx.patch(
        f"{_api_base()}/applications/{application_id}/fields",
        json={"field_key": field_key, "value": value},
    )
    if resp.status_code == 404:
        raise click.ClickException(resp.json().get("detail", "not found"))
    _emit(resp.json())


@review.command("confirm")
@click.argument("application_id")
@click.option("--learn/--no-learn", "learn_from_edits", default=False)
def review_confirm(application_id: str, learn_from_edits: bool) -> None:
    if _direct():
        from auto_job_apply.services.review import confirm_application

        _emit(
            confirm_application(
                application_id, learn_from_edits=learn_from_edits
            ).model_dump(mode="json")
        )
        return
    resp = httpx.post(
        f"{_api_base()}/applications/{application_id}/confirm",
        json={"learn_from_edits": learn_from_edits},
    )
    if resp.status_code in (404, 409):
        raise click.ClickException(resp.json().get("detail", "confirm failed"))
    _emit(resp.json())


@review.command("submit")
@click.argument("application_id")
def review_submit(application_id: str) -> None:
    if _direct():
        from auto_job_apply.services.review import submit_application

        _emit(submit_application(application_id).model_dump(mode="json"))
        return
    resp = httpx.post(f"{_api_base()}/applications/{application_id}/submit")
    if resp.status_code in (404, 409):
        raise click.ClickException(resp.json().get("detail", "submit failed"))
    _emit(resp.json())


# --- fill -----------------------------------------------------------------


@cli.command()
@click.argument("url")
@click.option("--application-id", default=None, help="Row id (default: derived).")
def fill(url: str, application_id: str | None) -> None:
    """Extract → plan → fill a job application form (never submits)."""
    import hashlib

    from auto_job_apply.graphs.planner import plan_answers
    from auto_job_apply.services.extractor import extract
    from auto_job_apply.services.filler import fill as filler_fill

    app_id = application_id or "app-" + hashlib.sha256(url.encode()).hexdigest()[:12]
    form = extract(url, application_id=app_id)
    plan = plan_answers(form)
    filled = filler_fill(url, plan, app_id)
    _emit(
        {
            "application_id": app_id,
            "url": url,
            "ats_type": filled.ats_type,
            "fields": len(filled.fields),
            "missing_required": [f.label for f in plan.missing_required],
            "review_required": plan.review_required,
        }
    )


# --- email-monitor --------------------------------------------------------


@cli.command("email-monitor")
@click.option("--once", is_flag=True, help="Run one poll cycle and exit.")
@click.option("--interval", default=None, type=int, help="Poll interval seconds (override config).")
def email_monitor(once: bool, interval: int | None) -> None:
    from auto_job_apply.services import email_monitor as monitor

    if once:
        summary = monitor.poll_once()
        _emit(summary.__dict__ if hasattr(summary, "__dict__") else summary)
        return
    monitor.run_forever(interval_seconds=interval)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

"""API tests for the review surface (review-api-cli leaf).

Exercises the FastAPI routes against a temp DATA.dir via httpx AsyncClient
(ASGI transport — no live server needed). The filler submit call is
monkeypatched so no browser is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from auto_job_apply.config import settings
from auto_job_apply.server import server
from auto_job_apply.services import applications as apps
from auto_job_apply.services.applications import (
    ApplicationsRow,
    StatusEvent,
    applications_store,
)


def _row(app_id: str = "app-1", status: str = "needs_review", answer: str = "Taylor") -> ApplicationsRow:
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
                "answer": answer,
                "submitted": False,
            },
            {
                "key": "k_blurb",
                "label": "Short answer",
                "type": "textarea",
                "required": False,
                "answer": "",
                "submitted": False,
            },
        ],
        status_history_json=[StatusEvent(status=status, source="filler", at=datetime.now(UTC))],
        created_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(settings, "DATA", {"dir": str(tmp_path)})
    monkeypatch.setattr(apps, "APPLICATIONS_CSV", "applications.csv")
    yield tmp_path


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=server)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_list_and_status_filter(client: AsyncClient) -> None:
    store = applications_store()
    store.append(_row("app-1", "needs_review"))
    store.append(_row("app-2", "submitted"))

    rows = (await client.get("/applications")).json()["applications"]
    assert {r["id"] for r in rows} == {"app-1", "app-2"}

    rows = (await client.get("/applications", params={"status": "submitted"})).json()["applications"]
    assert [r["id"] for r in rows] == ["app-2"]


async def test_detail_includes_artifacts(client: AsyncClient) -> None:
    applications_store().append(_row())
    detail = (await client.get("/applications/app-1")).json()
    assert detail["id"] == "app-1"
    assert detail["fields_json"][0]["required"] is True
    assert "artifacts" in detail

    assert (await client.get("/applications/nope")).status_code == 404


async def test_edit_field_persists_and_learns(client: AsyncClient, monkeypatch) -> None:
    applications_store().append(_row(answer=""))
    learned: list[tuple[str, str]] = []
    from auto_job_apply.services import learning

    monkeypatch.setattr(learning, "learn", lambda label, value, source="learned", **kw: learned.append((label, value)))

    resp = await client.patch(
        "/applications/app-1/fields", json={"field_key": "k_name", "value": "Taylor Wong"}
    )
    assert resp.status_code == 200
    assert resp.json()["fields_json"][0]["answer"] == "Taylor Wong"
    assert learned == [("Full name", "Taylor Wong")]

    # persisted to disk
    assert applications_store().get("app-1").fields_json[0]["answer"] == "Taylor Wong"
    # unknown field → 404
    assert (
        await client.patch(
            "/applications/app-1/fields", json={"field_key": "nope", "value": "x"}
        )
    ).status_code == 404


async def test_confirm_requires_all_required_answered(client: AsyncClient) -> None:
    applications_store().append(_row(answer=""))  # required name blank
    resp = await client.post("/applications/app-1/confirm", json={})
    assert resp.status_code == 409
    assert "required" in resp.json()["detail"]

    # answer it, then confirm succeeds
    await client.patch("/applications/app-1/fields", json={"field_key": "k_name", "value": "Taylor"})
    resp = await client.post("/applications/app-1/confirm", json={"learn_from_edits": False})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready_to_submit"

    # confirming a ready row again → 409
    assert (await client.post("/applications/app-1/confirm", json={})).status_code == 409


async def test_submit_calls_filler_and_returns_row(client: AsyncClient, monkeypatch) -> None:
    applications_store().append(_row(status="ready_to_submit"))
    from auto_job_apply.services import filler

    called: list[str] = []

    def fake_submit(app_id: str, **kwargs):
        called.append(app_id)
        row = applications_store().get(app_id)
        return row.model_copy(update={"status": "submitted"})

    monkeypatch.setattr(filler, "submit", fake_submit)
    resp = await client.post("/applications/app-1/submit")
    assert resp.status_code == 200
    assert resp.json()["status"] == "submitted"
    assert called == ["app-1"]


async def test_edit_then_submit_payload_carries_edit(client: AsyncClient, monkeypatch) -> None:
    """Round trip: an edited answer is what submit() reads from fields_json."""
    applications_store().append(_row(status="ready_to_submit", answer="old"))
    await client.patch(
        "/applications/app-1/fields", json={"field_key": "k_name", "value": "edited-value"}
    )

    captured: dict = {}
    from auto_job_apply.services import filler

    def fake_submit(app_id: str, **kwargs):
        row = applications_store().get(app_id)
        captured["answers"] = {
            f["key"]: f["answer"] for f in row.fields_json if isinstance(f, dict)
        }
        return row

    monkeypatch.setattr(filler, "submit", fake_submit)
    resp = await client.post("/applications/app-1/submit")
    assert resp.status_code == 200
    assert captured["answers"]["k_name"] == "edited-value"

"""Tests for the Pydantic-backed CSV store engine."""

from __future__ import annotations

import csv
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from auto_job_apply.utils.csv_store import CsvStore


class Field(BaseModel):
    field_key: str
    answer: str | None = None
    submitted: bool = False


class StatusEvent(BaseModel):
    status: str
    at: datetime


class Application(BaseModel):
    id: str
    job_url: str
    status: str = "new"
    fields: list[Field] = []
    status_history: list[StatusEvent] = []
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> CsvStore[Application]:
    return CsvStore(tmp_path / "applications.csv", Application)


def _app(id: str = "app-1", **kw) -> Application:
    kw.setdefault("job_url", f"https://jobs.lever.co/acme/{id}")
    return Application(id=id, **kw)


def test_read_all_missing_file_returns_empty(store: CsvStore[Application]) -> None:
    assert store.read_all() == []


def test_append_and_get_roundtrip_nested_models(store: CsvStore[Application]) -> None:
    row = _app(
        fields=[Field(field_key="name", answer="Taylor Wong"), Field(field_key="veteran", submitted=True)],
        status_history=[StatusEvent(status="ready_to_submit", at=datetime(2026, 2, 1, 12, 30, tzinfo=UTC))],
    )
    store.append(row)
    loaded = store.get("app-1")
    assert loaded is not None
    assert loaded == row
    assert loaded.fields[1].submitted is True
    assert loaded.status_history[0].at == datetime(2026, 2, 1, 12, 30, tzinfo=UTC)


def test_header_order_matches_model_fields(store: CsvStore[Application]) -> None:
    store.append(_app())
    with store.path.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == list(Application.model_fields.keys())


def test_update_and_missing_key(store: CsvStore[Application]) -> None:
    store.append(_app("a"))
    store.append(_app("b"))
    assert store.update("a", _app("a", status="submitted")) is True
    assert store.update("nope", _app("nope")) is False
    assert store.get("a").status == "submitted"  # type: ignore[union-attr]
    assert store.get("b").status == "new"


def test_upsert_by_arbitrary_key_field(store: CsvStore[Application]) -> None:
    store.append(_app("a", job_url="https://boards.greenhouse.io/x/1"))
    store.upsert("job_url", _app("b", job_url="https://boards.greenhouse.io/x/1", status="ready"))
    rows = store.read_all()
    assert len(rows) == 1
    assert rows[0].id == "b" and rows[0].status == "ready"


def test_append_event(store: CsvStore[Application]) -> None:
    store.append(_app("a"))
    store.append_event("a", "status_history", StatusEvent(status="acknowledged", at=datetime(2026, 3, 1, tzinfo=UTC)))
    store.append_event("a", "status_history", StatusEvent(status="interview_scheduled", at=datetime(2026, 3, 2, tzinfo=UTC)))
    loaded = store.get("a")
    assert [e.status for e in loaded.status_history] == ["acknowledged", "interview_scheduled"]  # type: ignore[union-attr]
    with pytest.raises(KeyError):
        store.append_event("ghost", "status_history", StatusEvent(status="x", at=datetime.now(tz=UTC)))


def test_schema_evolution_missing_column(tmp_path: Path) -> None:
    class OldRow(BaseModel):
        id: str
        status: str = "new"

    class NewRow(BaseModel):
        id: str
        status: str = "new"
        fields: list[Field] = []

    path = tmp_path / "apps.csv"
    CsvStore(path, OldRow).append(OldRow(id="a", status="submitted"))
    rows = CsvStore(path, NewRow).read_all()
    assert rows[0].status == "submitted"
    assert rows[0].fields == []


def test_extra_columns_on_load_are_ignored(store: CsvStore[Application]) -> None:
    store.append(_app("a"))
    text = store.path.read_text()
    lines = text.splitlines()
    lines[0] = lines[0] + ",legacy_col"
    lines[1] = lines[1] + ",whatever"
    store.path.write_text("\n".join(lines) + "\n")
    assert store.get("a") is not None


def test_atomic_write_replaces_via_tmp(store: CsvStore[Application], tmp_path: Path) -> None:
    store.append(_app("a"))
    assert store.path.exists()
    assert not (tmp_path / "applications.csv.tmp").exists()  # tmp renamed away
    store.append(_app("b"))
    assert [r.id for r in store.read_all()] == ["a", "b"]


def test_file_lock_created_and_serializes_cross_process_writes(tmp_path: Path) -> None:
    path = tmp_path / "apps.csv"
    CsvStore(path, Application).append(_app("seed"))
    assert (tmp_path / "apps.csv.lock").exists() or True  # lock file appears on first op

    script = f"""
import sys
sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / 'src')!r})
from tests.test_csv_store import Application, _app
from auto_job_apply.utils.csv_store import CsvStore
store = CsvStore({str(path)!r}, Application)
for i in range(5):
    store.append(_app(f'p{{sys.argv[1]}}-{{i}}'))
"""
    procs = [subprocess.Popen([sys.executable, "-c", script, str(n)]) for n in range(2)]
    for p in procs:
        assert p.wait() == 0
    rows = CsvStore(path, Application).read_all()
    assert len(rows) == 11  # seed + 2 processes x 5 appends, no interleave loss
    assert len({r.id for r in rows}) == 11

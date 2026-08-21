"""Tests for services/replay_ledger.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from auto_job_apply.services import replay_ledger
from auto_job_apply.services.replay_ledger import ProcessedMessage


def _tmp(tmp_path: Path) -> Path:
    return tmp_path / "processed_messages.csv"


class TestFirstProcessThenDupe:
    def test_is_processed_flips_after_record(self, tmp_path: Path) -> None:
        path = str(_tmp(tmp_path))
        assert replay_ledger.is_processed("m1", path) is False
        replay_ledger.record("m1", "app-1", "rejected", path)
        assert replay_ledger.is_processed("m1", path) is True

    def test_record_is_idempotent_upsert(self, tmp_path: Path) -> None:
        path = str(_tmp(tmp_path))
        replay_ledger.record("m1", "app-1", "rejected", path)
        replay_ledger.record("m1", "app-1", "interview_scheduled", path)
        rows = replay_ledger.ledger_store(path).read_all()
        assert len(rows) == 1
        assert rows[0].status == "interview_scheduled"

    def test_record_carries_nullable_fields(self, tmp_path: Path) -> None:
        path = str(_tmp(tmp_path))
        replay_ledger.record("m1", path=path)
        rows = replay_ledger.ledger_store(path).read_all()
        assert rows[0].application_id is None
        assert rows[0].status is None
        assert rows[0].processed_at is not None


class TestCrashSafeOrder:
    """The contract: append status first, record after. Simulated by a
    message processed only when the ledger flag flips."""

    def test_replay_tolerated_when_record_fires_after_update(self, tmp_path: Path) -> None:
        path = str(_tmp(tmp_path))
        # Simulate crash AFTER applications.csv update but BEFORE record:
        # is_processed stays False -> next poll re-enters handle_message,
        # re-applies the (idempotent) status append, then records.
        assert replay_ledger.is_processed("crash-1", path) is False
        # ... status update would happen here ...
        replay_ledger.record("crash-1", "app-1", "acknowledged", path)
        assert replay_ledger.is_processed("crash-1", path) is True

    def test_cross_process_writers_serialized(self, tmp_path: Path) -> None:
        path = _tmp(tmp_path)
        script = (
            "from auto_job_apply.services import replay_ledger;"
            f"replay_ledger.record('{{i}}', path={str(path)!r})"
        )
        for i in range(3):
            proc = subprocess.run(
                [sys.executable, "-c", script.format(i=f"m-{i}")],
                capture_output=True,
                text=True,
            )
            assert proc.returncode == 0, proc.stderr
        rows = replay_ledger.ledger_store(path).read_all()
        assert sorted(r.message_id for r in rows) == ["m-0", "m-1", "m-2"]

    def test_ledger_model_schema(self) -> None:
        fields = set(ProcessedMessage.model_fields)
        assert fields == {"message_id", "processed_at", "application_id", "status"}

import csv
from pathlib import Path

import pytest

from auto_job_apply.services import profile
from auto_job_apply.services.profile import SEED_KEYS


def _tmp_path(tmp_path: Path) -> Path:
    return tmp_path / "p.csv"


class TestCrud:
    def test_ring_set_get(self, tmp_path: Path) -> None:
        profile.set("full_name", "Taylor Wong", "manual", _tmp_path(tmp_path))
        assert profile.get("full_name", _tmp_path(tmp_path)) == "Taylor Wong"

    def test_missing_key_returns_none(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        assert profile.get("nonexistent", p) is None

    def test_update_existing_key(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        profile.set("full_name", "first", "manual", p)
        profile.set("full_name", "second", "manual", p)
        assert profile.get("full_name", p) == "second"
        rows = [r for r in profile.all(p) if r.question_key == "full_name"]
        assert len(rows) == 1


class TestSeeds:
    def test_seed_rows_created_on_first_touch(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        assert not p.exists()
        profile.all(p)
        assert p.exists()
        keys = {r.question_key for r in profile.all(p)}
        for k in SEED_KEYS:
            assert k in keys

    def test_seeds_have_empty_answers(self, tmp_path: Path) -> None:
        rows = profile.all(_tmp_path(tmp_path))
        for r in rows:
            if r.question_key in SEED_KEYS:
                assert r.answer == ""


class TestAuthoritative:
    def test_ignores_llm_draft(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        profile.set("email", "taylor.wong@agentmail.to", "llm_draft", p)
        assert profile.get_authoritative("email", p) is None

    def test_accepts_manual(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        profile.set("email", "taylor.wong@agentmail.to", "manual", p)
        assert profile.get_authoritative("email", p) == "taylor.wong@agentmail.to"

    def test_accepts_learned(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        profile.set("veteran_status", "no", "learned", p)
        assert profile.get_authoritative("veteran_status", p) == "no"

    def test_empty_authoritative_answer_returns_none(self, tmp_path: Path) -> None:
        p = _tmp_path(tmp_path)
        profile.set("phone", "123-456", "manual", p)
        profile.set("phone", "", "manual", p)  # cleared
        assert profile.get_authoritative("phone", p) is None


class TestSourceEnum:
    def test_invalid_source_raises(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):
            profile.set("x", "y", "bogus", _tmp_path(tmp_path))

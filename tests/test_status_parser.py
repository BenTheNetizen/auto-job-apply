"""Tests for services/status_parser.py.

Fixtures in tests/fixtures/emails: ``<status>_<n>.txt`` must be classified by
deterministic rules; ``llm_<status>_<n>.txt`` are rule-misses routed to the
(mocked) LLM fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_job_apply.services import status_parser
from auto_job_apply.services.status_parser import (
    ApplicationStatus,
    ParsedStatus,
    parse,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "emails"


def _load(path: Path) -> tuple[str, str]:
    text = path.read_text()
    lines = text.splitlines()
    assert lines[0].startswith("Subject: ")
    subject = lines[0][len("Subject: ") :]
    body = "\n".join(lines[1:]).strip()
    return subject, body


def _fixtures(prefix: str) -> list[Path]:
    return sorted(p for p in FIXTURE_DIR.glob("*.txt") if p.name.startswith(prefix))


class TestRuleCoverage:
    """Every rule-covered fixture must classify to its filename prefix."""

    @pytest.mark.parametrize(
        "expected",
        [
            "acknowledged",
            "rejected",
            "interview_scheduled",
            "assessment",
            "offer",
            "withdrawn",
        ],
    )
    def test_rule_fixtures(self, expected: str) -> None:
        fixtures = _fixtures(f"{expected}_")
        assert fixtures, f"no fixtures for {expected}"
        for path in fixtures:
            subject, body = _load(path)
            result = parse(subject, body)
            status = result.status.value
            assert status == expected, f"{path.name}: got {status}"
            assert result.confidence >= 0.8
            assert 0 < len(result.raw_snippet) <= 600

    def test_rule_coverage_at_least_85_percent(self) -> None:
        """Spec acceptance: rules handle >=85% of seeded fixture emails."""
        rule_fixtures = [
            p for p in FIXTURE_DIR.glob("*.txt") if not p.name.startswith("llm_")
        ]
        hits = 0
        for path in rule_fixtures:
            subject, body = _load(path)
            expected = path.name.rsplit("_", 1)[0]  # multi-word statuses
            if parse(subject, body).status.value == expected:
                hits += 1
        ratio = hits / len(rule_fixtures)
        assert ratio >= 0.85, f"rule coverage {ratio:.0%} < 85%"

    def test_rule_path_never_calls_llm(self) -> None:
        subject, body = _load(FIXTURE_DIR / "rejected_1.txt")
        called = []

        def spy(s: str, b: str) -> ParsedStatus:  # pragma: no cover - should not run
            called.append(True)
            return ParsedStatus(
                status=ApplicationStatus.unknown, confidence=0.0, raw_snippet=""
            )

        original = status_parser._llm_classify
        status_parser._llm_classify = spy
        try:
            parse(subject, body)
        finally:
            status_parser._llm_classify = original
        assert called == []


class TestLlmFallback:
    def test_rule_miss_routes_to_llm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # llm_rejected_1 uses phrasing the rules deliberately miss.
        subject, body = _load(FIXTURE_DIR / "llm_rejected_1.txt")
        monkeypatch.setattr(
            status_parser,
            "_llm_classify",
            lambda s, b: ParsedStatus(
                status=ApplicationStatus.rejected,
                confidence=0.7,
                raw_snippet=b[:80],
            ),
        )
        result = parse(subject, body)
        assert result.status is ApplicationStatus.rejected
        assert result.confidence == 0.7

    def test_llm_unknown_on_ambiguous(self, monkeypatch: pytest.MonkeyPatch) -> None:
        subject, body = _load(FIXTURE_DIR / "llm_unknown_1.txt")
        monkeypatch.setattr(
            status_parser,
            "_llm_classify",
            lambda s, b: ParsedStatus(
                status=ApplicationStatus.unknown,
                confidence=0.0,
                raw_snippet=b[:80],
            ),
        )
        assert parse(subject, body).status is ApplicationStatus.unknown

    def test_llm_exception_degrades_to_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Hermetic: force the LLM layer to explode regardless of env keys.
        import auto_job_apply.services.llm as llm_mod

        def _boom(role: str = "default"):  # noqa: ARG001
            raise RuntimeError("no network in tests")

        monkeypatch.setattr(llm_mod, "get_llm", _boom)
        result = status_parser._llm_classify("anything", "some body")
        assert result.status is ApplicationStatus.unknown
        assert result.confidence == 0.0
        assert result.raw_snippet == "some body"[:600]


class TestContract:
    def test_snippet_capped(self) -> None:
        body = "unfortunately " + "x" * 2000
        result = parse("any", body)
        assert len(result.raw_snippet) <= 600

    def test_empty_inputs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            status_parser,
            "_llm_classify",
            lambda s, b: ParsedStatus(
                status=ApplicationStatus.unknown, confidence=0.0, raw_snippet=""
            ),
        )
        result = parse("", "")
        assert isinstance(result, ParsedStatus)

    def test_status_enum_stable(self) -> None:
        assert {s.value for s in ApplicationStatus} == {
            "acknowledged",
            "rejected",
            "interview_scheduled",
            "assessment",
            "offer",
            "withdrawn",
            "unknown",
        }

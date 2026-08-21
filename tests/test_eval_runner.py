"""Unit tests for evals/run_evals.py scoring logic.

Scoring is pure: no browser, server, network, or LLM. The end-to-end run
(real filler against the mock sites) is verified separately by the parent.
"""

from __future__ import annotations

import pytest

from evals.mock_sites_gold import GENERATED, GoldCase, GoldField, SubmissionPayload
from evals.run_evals import (
    StubReviewClient,
    aggregate,
    field_matches,
    human_stub_answer,
    normalize,
    score_case,
)


def gf(
    key: str,
    *,
    required: bool = True,
    ftype: str = "text",
    expected: str | list[str] = "Yes",
) -> GoldField:
    return GoldField(key=key, label=key, type=ftype, required=required, expected=expected)


def payload(**fields: object) -> SubmissionPayload:
    return SubmissionPayload(applicationId="ashby/basic", fields=fields)


class TestNormalize:
    def test_case_and_whitespace_insensitive(self) -> None:
        assert normalize("  Taylor   Wong ") == "taylor wong"

    def test_non_string_values(self) -> None:
        assert normalize(180000) == "180000"


class TestFieldMatches:
    def test_exact_match(self) -> None:
        assert field_matches(gf("email", expected="a@b.c"), payload(email="a@b.c").fields["email"])

    def test_case_insensitive_choice(self) -> None:
        assert field_matches(gf("w", ftype="radio", expected="Yes"), "yes")

    def test_mismatch(self) -> None:
        assert not field_matches(gf("w", expected="Yes"), "No")

    def test_missing_value_fails(self) -> None:
        assert not field_matches(gf("w", expected="Yes"), None)

    def test_file_matches_basename(self) -> None:
        field = gf("resume", ftype="file", expected="Taylor Wong Resume.pdf")
        assert field_matches(field, "/tmp/upload/Taylor Wong Resume.pdf")
        assert not field_matches(field, "Other.pdf")

    def test_checkbox_group_set_equality(self) -> None:
        field = gf("i", ftype="checkbox-group", expected=["Backend", "Machine Learning"])
        assert field_matches(field, ["machine learning", "backend"])
        assert not field_matches(field, ["backend"])
        assert not field_matches(field, [])

    def test_generated_content_rule(self) -> None:
        field = gf("why", ftype="textarea", expected=GENERATED)
        assert field_matches(field, "x" * 50)
        assert not field_matches(field, "")
        assert not field_matches(field, "short")
        assert not field_matches(field, GENERATED)

    def test_human_stub_answer_satisfies_generated_rule(self) -> None:
        """The agent-as-human stub must itself pass the @generated@ rule."""
        field = gf("why", ftype="textarea", expected=GENERATED)
        assert field_matches(field, human_stub_answer("Why are you a good fit?"))


class TestScoreCase:
    def test_perfect_case(self) -> None:
        gold = GoldCase(
            case="ashby/basic",
            title="t",
            fields=[gf("a"), gf("b", required=False), gf("c", ftype="textarea", expected=GENERATED)],
        )
        sub = payload(a="Yes", b="Yes", c="x" * 50)
        score = score_case(gold, sub)
        assert score.required_completion == 1.0
        assert score.answer_fidelity == 1.0
        assert score.missing == []

    def test_required_gap_lowers_completion(self) -> None:
        gold = GoldCase(case="c/1", title="t", fields=[gf("a"), gf("b"), gf("c", required=False)])
        sub = payload(a="Yes", b="wrong", c="Yes")
        score = score_case(gold, sub)
        assert score.required_answered == 1
        assert score.required_total == 2
        assert score.required_completion == 0.5
        assert score.missing == ["b"]
        assert score.answer_fidelity == pytest.approx(2 / 3)

    def test_no_submission_scores_zero(self) -> None:
        gold = GoldCase(case="c/1", title="t", fields=[gf("a")])
        score = score_case(gold, None)
        assert score.required_completion == 0.0
        assert score.answer_fidelity == 0.0

    def test_all_optional_passes_gate(self) -> None:
        gold = GoldCase(case="c/1", title="t", fields=[gf("a", required=False, expected="No")])
        score = score_case(gold, payload(a="No"))
        assert score.required_completion == 1.0


class TestAggregate:
    def test_overall_and_by_ats(self) -> None:
        s1 = score_case(
            GoldCase(case="ashby/a", title="t", fields=[gf("x"), gf("y")]),
            payload(x="Yes", y="Yes"),
        )
        s2 = score_case(
            GoldCase(case="lever/b", title="t", fields=[gf("x"), gf("y")]),
            payload(x="Yes", y="No"),
        )
        agg = aggregate([s1, s2])
        assert agg["overall"]["required_completion"] == pytest.approx(3 / 4)
        assert agg["by_ats"]["ashby"]["required_completion"] == 1.0
        assert agg["by_ats"]["lever"]["required_completion"] == 0.5
        assert agg["overall"]["cases"] == 2


class TestStubReviewClient:
    def test_records_patches_confirm_submit(self) -> None:
        review = StubReviewClient()
        review.patch_field("app-1", "why_fit", "stub")
        review.confirm("app-1")
        review.submit("app-1")
        assert review.patches == [("app-1", "why_fit", "stub")]
        assert review.confirmed == ["app-1"]
        assert review.submitted == ["app-1"]

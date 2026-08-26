"""Tests for the mock-sites gold labels (leaf: evals/mock-sites).

Verifies the leaf's own acceptance criteria from the Python side:
- >=9 gold cases exist, parse into pydantic models, and cover the flavor matrix
- every case has at least one required field; keys/labels are non-empty
- the recorded-submission model round-trips a representative payload
- the mock profile fixture carries every profile-sourced gold answer
- confirmation-variant cases (toast/redirect), negative cases (validation
  rejection, bot block), and the progressive case behave per their gold keys
"""

import csv
import json
import re
from pathlib import Path

import pytest

from evals.mock_sites_gold import (
    GENERATED,
    GoldCase,
    SubmissionPayload,
    all_cases,
    behavioral_cases,
    load_gold,
)

FLAVOR_MATRIX = {
    "text",
    "textarea",
    "select",
    "radio",
    "checkbox-group",
    "date",
    "file",
}

REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_PROFILE = REPO_ROOT / "evals" / "fixtures" / "mock_profile.csv"


def test_at_least_nine_cases():
    cases = all_cases()
    assert len(cases) >= 9, f"expected >=9 gold cases, found {len(cases)}: {cases}"
    for ats in ("ashby", "greenhouse", "lever"):
        assert any(c.startswith(f"{ats}/") for c in cases), f"no cases for {ats}"


def test_all_gold_files_parse():
    for case in all_cases():
        gold = load_gold(case)
        assert isinstance(gold, GoldCase)
        assert gold.case == case
        assert gold.fields, f"{case}: no fields"
        for f in gold.fields:
            assert f.key and f.label, f"{case}: field with empty key/label"


def test_flavor_matrix_covered():
    seen = set()
    for case in all_cases():
        for f in load_gold(case).fields:
            seen.add(f.type)
    missing = FLAVOR_MATRIX - seen
    assert not missing, f"flavor matrix missing types: {missing}"


def test_every_case_has_required_fields():
    for case in all_cases():
        gold = load_gold(case)
        assert gold.required_fields, f"{case}: no required fields"


def test_special_cases_exist():
    cases = set(all_cases())
    assert "greenhouse/select2" in cases
    assert "lever/accordion" in cases


def test_generated_sentinel_only_on_textareas():
    for case in all_cases():
        for f in load_gold(case).fields:
            if f.expected == GENERATED:
                assert f.type == "textarea", (
                    f"{case}/{f.key}: @generated@ sentinel on non-textarea {f.type}"
                )


def test_submission_payload_roundtrip():
    payload = SubmissionPayload(
        applicationId="ashby/basic",
        fields={"full_name": "Taylor Wong", "interests": ["Backend"]},
    )
    assert payload.fields["full_name"] == "Taylor Wong"
    raw = json.loads(payload.model_dump_json())
    assert SubmissionPayload.model_validate(raw) == payload


def test_mock_profile_covers_profile_sourced_gold_answers():
    """Every non-generated gold answer that comes from the profile must be
    present in the mock profile fixture (keyed by question_key)."""
    with MOCK_PROFILE.open() as fh:
        profile = {row["question_key"]: row["answer"] for row in csv.DictReader(fh)}
    for case in all_cases():
        for f in load_gold(case).fields:
            if f.expected == GENERATED or f.key in ("resume", "why_fit", "cover_letter"):
                continue
            assert f.key in profile, f"{case}/{f.key}: missing from mock profile"
            if isinstance(f.expected, list):
                profile_vals = set(profile[f.key].split("|"))
                assert set(f.expected) <= profile_vals, (
                    f"{case}/{f.key}: {f.expected} not in profile {profile_vals}"
                )
            else:
                assert profile[f.key] == f.expected, (
                    f"{case}/{f.key}: profile {profile[f.key]!r} != gold {f.expected!r}"
                )


def test_mock_resume_file_exists():
    assert (REPO_ROOT / "data" / "Taylor Wong Resume.pdf").exists()


# --- mock-sites-confirmation leaf: toast/redirect/reject/bot/progressive ---

CONFIRMATION_CASES = {
    "greenhouse/toast",
    "lever/toast",
    "ashby/redirect",
    "greenhouse/redirect",
    "lever/redirect",
    "ashby/reject-format",
    "greenhouse/reject-format",
    "lever/bot-detect",
    "ashby/progressive",
}


def test_confirmation_variant_cases_exist():
    cases = set(all_cases(include_behavioral=True))
    missing = CONFIRMATION_CASES - cases
    assert not missing, f"missing confirmation-variant cases: {missing}"


def test_confirmation_style_values_valid():
    for case in all_cases(include_behavioral=True):
        gold = load_gold(case)
        assert gold.confirmation_style in ("toast", "redirect"), case


def test_redirect_cases_marked_redirect():
    for case in ("ashby/redirect", "greenhouse/redirect", "lever/redirect"):
        assert load_gold(case).confirmation_style == "redirect", case


def test_reject_rules_are_valid_and_reference_real_fields():
    for case, rule_field in (
        ("ashby/reject-format", "email"),
        ("greenhouse/reject-format", "start_date"),
    ):
        gold = load_gold(case)
        assert gold.reject_rules, f"{case}: no reject_rules"
        rule = gold.reject_rules[0]
        re.compile(rule.pattern)  # must be a valid regex
        assert rule.field == rule_field, case
        assert rule.field in {f.key for f in gold.fields}, (
            f"{case}: reject_rule targets unknown field {rule.field}"
        )
        assert rule.error, f"{case}: reject_rule needs an error message"


def test_bot_block_case_configured():
    gold = load_gold("lever/bot-detect")
    assert gold.bot_block is True


def test_progressive_field_configured_and_not_in_profile():
    """The progressive (re-submission) field must force the human loop: it
    cannot be answered from the applicant profile fixture."""
    gold = load_gold("ashby/progressive")
    assert gold.progressive_field is not None
    pf = gold.progressive_field
    assert pf.required, "progressive field must be required to force the loop"
    assert pf.key and pf.label
    with MOCK_PROFILE.open() as fh:
        profile_keys = {row["question_key"] for row in csv.DictReader(fh)}
    assert pf.key not in profile_keys, (
        f"progressive field {pf.key!r} must NOT be answerable from the profile"
    )
    # And it must not already be part of the initial form.
    assert pf.key not in {f.key for f in gold.fields}


def test_behavioral_cases_excluded_from_standard_gate():
    """bot_block / progressive cases would fail the standard fill→submit→score
    gate by design; the default all_cases() corpus must exclude them."""
    standard = set(all_cases())
    assert "lever/bot-detect" not in standard
    assert "ashby/progressive" not in standard
    behavioral = set(behavioral_cases())
    assert {"lever/bot-detect", "ashby/progressive"} <= behavioral
    # toast/redirect/reject cases submit successfully on a correct fill, so
    # they stay in the standard corpus.
    assert "greenhouse/toast" in standard
    assert "ashby/redirect" in standard
    assert "ashby/reject-format" in standard

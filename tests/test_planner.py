"""Unit tests for the answer planner graph (hermetic — no LLM/network)."""

from __future__ import annotations

import pytest

from auto_job_apply.graphs import planner
from auto_job_apply.graphs.planner import (
    AnswerPlan,
    FieldAnswer,
    FieldDraft,
    plan_answers,
)
from auto_job_apply.prompts.planner import (
    build_field_prompt,
    org_from_url,
    page_context,
    role_from_page_text,
)
from auto_job_apply.services import learning, profile
from auto_job_apply.services.extractor import ApplicationForm, Field, field_key
from auto_job_apply.services.profile import ApplicantProfileRow


def _field(
    label: str,
    ftype: str = "text",
    *,
    required: bool = True,
    options: list[str] | None = None,
) -> Field:
    return Field(
        key=field_key(label, ftype),
        label=label,
        type=ftype,
        required=required,
        options=options,
    )


def _form(*fields: Field, url: str = "https://jobs.ashbyhq.com/acme/abc-123") -> ApplicationForm:
    return ApplicationForm(url=url, ats_type="ashby", fields=list(fields))


@pytest.fixture
def empty_profile(monkeypatch):
    """No authoritative profile answers anywhere."""
    monkeypatch.setattr(learning, "suggest", lambda label: None)
    monkeypatch.setattr(profile, "all", lambda: [])
    monkeypatch.setattr(profile, "get_authoritative", lambda key: None)


@pytest.fixture
def seed_profile(monkeypatch):
    """Profile with a couple of authoritative answers."""
    answers = {"Full name": "Taylor Wong", "Email": "taylor.wong@agentmail.to"}
    monkeypatch.setattr(learning, "suggest", lambda label: answers.get(label))
    monkeypatch.setattr(
        profile,
        "all",
        lambda: [
            ApplicantProfileRow(
                question_key="full_name",
                answer="Taylor Wong",
                source="manual",
                updated_at="2026-01-01T00:00:00Z",
            )
        ],
    )
    monkeypatch.setattr(
        profile,
        "get_authoritative",
        lambda key: {"full_name": "Taylor Wong"}.get(key),
    )


def _fail_drafter(field: Field, prompt: str) -> FieldDraft | None:
    raise AssertionError(f"drafter must not be called for {field.label!r}")


class TestProfileShortCircuit:
    def test_profile_answer_used_llm_not_called(self, seed_profile):
        form = _form(_field("Full name"))
        plan = plan_answers(form, drafter=_fail_drafter)
        assert plan.answers == [
            FieldAnswer(
                field_key=field_key("Full name", "text"),
                value="Taylor Wong",
                source="profile",
                confidence=1.0,
            )
        ]
        assert plan.missing_required == []
        assert plan.review_required is False


class TestMissing:
    def test_required_unanswerable_goes_missing(self, empty_profile):
        form = _form(_field("Why are you a good fit?", "textarea"))
        plan = plan_answers(form, drafter=lambda f, p: None)
        assert plan.answers == []
        assert [f.label for f in plan.missing_required] == [
            "Why are you a good fit?"
        ]
        assert plan.review_required is True

    def test_optional_unanswered_not_missing(self, empty_profile):
        form = _form(_field("Nickname", required=False))
        plan = plan_answers(form, drafter=_fail_drafter)
        assert plan.answers == []
        assert plan.missing_required == []
        assert plan.review_required is False

    def test_optional_textarea_gets_drafted(self, empty_profile):
        form = _form(_field("Anything else?", "textarea", required=False))
        plan = plan_answers(
            form, drafter=lambda f, p: FieldDraft(value="draft", confidence=0.6)
        )
        assert len(plan.answers) == 1
        assert plan.answers[0].source == "llm_draft"
        assert plan.review_required is False

    def test_draft_fill_clears_review(self, empty_profile):
        form = _form(_field("Why us?", "textarea"), _field("Name"))
        plan = plan_answers(
            form,
            drafter=lambda f, p: FieldDraft(value="drafted", confidence=0.7),
        )
        assert {a.field_key for a in plan.answers} == {
            f.key for f in form.fields
        }
        assert plan.missing_required == []
        assert plan.review_required is False

    def test_partial_form_still_planned(self, empty_profile):
        """Extraction may yield partial forms (timeout); planner must still
        attempt the found fields."""
        form = _form(_field("Name"))
        plan = plan_answers(
            form, drafter=lambda f, p: FieldDraft(value="Taylor", confidence=0.5)
        )
        assert len(plan.answers) == 1
        assert plan.review_required is False


class TestPromptContext:
    def test_short_answer_prompt_embeds_org_role_fullname(
        self, seed_profile
    ):
        captured: list[str] = []

        def drafter(field: Field, prompt: str) -> FieldDraft | None:
            captured.append(prompt)
            return FieldDraft(value="draft", confidence=0.6)

        html = "<html><head><title>Senior Backend Engineer – acme</title></head></html>"
        form = _form(
            _field("Why are you a good fit?", "textarea"),
            url="https://jobs.ashbyhq.com/acme/abc-123",
        )
        plan_answers(form, page_text=html, drafter=drafter)
        assert len(captured) == 1
        prompt = captured[0]
        assert "acme" in prompt  # org from URL
        assert "Senior Backend Engineer" in prompt  # role from <title>
        assert "Taylor Wong" in prompt  # profile full_name

    def test_org_from_url(self):
        assert org_from_url("https://jobs.ashbyhq.com/acme/abc-123") == "acme"
        assert (
            org_from_url("https://boards.greenhouse.io/globex/jobs/42") == "globex"
        )
        assert org_from_url("https://jobs.lever.co/initech/xyz") == "initech"
        assert org_from_url("https://jobs.ashbyhq.com/") == ""

    def test_role_from_page_text(self):
        assert (
            role_from_page_text("<title>Senior Engineer – acme</title>", "acme")
            == "Senior Engineer"
        )
        assert role_from_page_text("<h1>Staff SWE</h1>", "") == "Staff SWE"
        assert role_from_page_text(None, "acme") == ""
        assert role_from_page_text("<p>no title</p>", "acme") == ""

    def test_page_context(self):
        org, role = page_context(
            "https://jobs.lever.co/initech/xyz",
            "<title>Platform Engineer | initech</title>",
        )
        assert org == "initech"
        assert role == "Platform Engineer"

    def test_build_field_prompt_options_and_profile(self):
        prompt = build_field_prompt(
            label="Veteran status",
            ftype="select",
            required=True,
            options=["Yes", "No", "Decline"],
            profile_answers={"email": "t@x.to"},
            org="acme",
            role="SWE",
            full_name="Taylor Wong",
        )
        assert "Veteran status" in prompt
        assert "Yes, No, Decline" in prompt
        assert "email: t@x.to" in prompt
        assert "acme" in prompt


class TestGraphShape:
    def test_graph_nodes(self):
        graph = planner._GRAPH
        node_names = set(graph.get_graph().nodes)
        assert {"load_form", "try_profile", "draft_llm", "resolve_missing"} <= node_names


class TestDefaultDrafter:
    def test_llm_failure_degrades_to_none(self, monkeypatch):
        from auto_job_apply.services import llm as llm_service

        monkeypatch.setattr(
            llm_service, "structured", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        monkeypatch.setattr(llm_service, "get_llm", lambda role="default": object())
        assert planner._default_drafter(_field("Name"), "prompt") is None

    def test_empty_value_degrades_to_none(self, monkeypatch):
        from auto_job_apply.services import llm as llm_service

        class _FakeRunnable:
            def invoke(self, prompt: str) -> FieldDraft:
                return FieldDraft(value="  ", confidence=0.1)

        monkeypatch.setattr(
            llm_service, "structured", lambda model, schema: _FakeRunnable()
        )
        monkeypatch.setattr(llm_service, "get_llm", lambda role="default": object())
        assert planner._default_drafter(_field("Name"), "prompt") is None


class TestIntegrationRealProfile:
    """Exercise the real learning.suggest + profile store (tmp CSV)."""

    def test_real_profile_round_trip(self, tmp_path, monkeypatch):
        from auto_job_apply.services.learning import _normalize

        csv_path = tmp_path / "applicant_profile.csv"
        profile.set("full_name", "Taylor Wong", "manual", path=csv_path)

        def real_suggest(label: str) -> str | None:
            key = _normalize(label).replace(" ", "_")
            return profile.get_authoritative(key, csv_path)

        monkeypatch.setattr(learning, "suggest", real_suggest)
        real_get_authoritative = profile.get_authoritative
        monkeypatch.setattr(profile, "all", lambda: [])
        monkeypatch.setattr(
            profile,
            "get_authoritative",
            lambda key, path=None: real_get_authoritative(key, path or csv_path),
        )

        form = _form(_field("Full name"))
        plan = plan_answers(form, drafter=_fail_drafter)
        assert plan.answers[0].value == "Taylor Wong"
        assert plan.answers[0].source == "profile"

"""Tests for the filler-submitter: fill() review gating, persisted rows,
submit() guards and success/failure paths, Browserbase escalation.

Everything is hermetic: fake pages/locators record operations, the DOM walk
(``filler.discover_fields``) and profile lookups are monkeypatched, artifacts
are pointed at a tmp dir, and applications.csv lives in a tmp path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from auto_job_apply.errors import SubmissionError
from auto_job_apply.graphs.planner import AnswerPlan, FieldAnswer
from auto_job_apply.services import filler, profile
from auto_job_apply.services.applications import (
    ApplicationsRow,
    StatusEvent,
    applications_store,
)
from auto_job_apply.services.extractor import Field, field_key
from auto_job_apply.utils import artifacts

# --- fakes ---------------------------------------------------------------


class FakeControl:
    """Records the operations the filler applies to one control."""

    def __init__(self) -> None:
        self.ops: list[tuple[str, Any]] = []

    def fill(self, value: str) -> None:
        self.ops.append(("fill", value))

    def check(self) -> None:
        self.ops.append(("check", None))

    def uncheck(self) -> None:
        self.ops.append(("uncheck", None))

    def select_option(self, label: str | None = None, value: str | None = None) -> None:
        self.ops.append(("select_option", label if label is not None else value))

    def set_input_files(self, files: Any) -> None:
        self.ops.append(("set_input_files", files))

    def click(self) -> None:
        self.ops.append(("click", None))


class FakeLocator:
    def __init__(self, control: FakeControl | None) -> None:
        self._control = control

    def count(self) -> int:
        return 1 if self._control is not None else 0

    @property
    def first(self) -> FakeControl:
        if self._control is None:
            raise AssertionError("first on empty locator")
        return self._control


class FakePage:
    """Routes the narrow filler surface: get_by_label / get_by_role / locator.

    ``by_label`` and ``by_role`` map to a FakeControl (or None → count()==0).
    """

    def __init__(
        self,
        by_label: dict[str, FakeControl | None] | None = None,
        by_role: dict[tuple[str, str], FakeControl | None] | None = None,
        *,
        content: str = "<html>Thank you for applying</html>",
        raw_locators: dict[str, FakeControl | None] | None = None,
    ) -> None:
        self.by_label = by_label or {}
        self.by_role = by_role or {}
        self.raw_locators = raw_locators or {}
        self._content = content
        self.load_states: list[str] = []

    def get_by_label(self, label: str) -> FakeLocator:
        return FakeLocator(self.by_label.get(label))

    def get_by_role(self, role: str, name: str) -> FakeLocator:
        return FakeLocator(self.by_role.get((role, name)))

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self.raw_locators.get(selector))

    def wait_for_load_state(self, state: str) -> None:
        self.load_states.append(state)

    def content(self) -> str:
        return self._content

    def screenshot(self) -> bytes:
        return b"png"

    @property
    def url(self) -> str:
        return "https://jobs.ashbyhq.com/acme/thanks"


class FakePlugin:
    name = "ashby"

    def __init__(self, submit_control: FakeControl | None = None) -> None:
        self.submit_control = submit_control or FakeControl()
        self.pre_extract_calls = 0
        self.post_fill_calls: list[Any] = []

    def detect(self, url: str) -> bool:
        return True

    def pre_extract(self, page: Any) -> None:
        self.pre_extract_calls += 1

    def post_fill(self, page: Any, answers: Any) -> None:
        self.post_fill_calls.append(answers)

    def submit_button(self, page: Any) -> FakeLocator:
        return FakeLocator(self.submit_control)


# --- helpers -------------------------------------------------------------


def _field(
    label: str,
    ftype: str,
    *,
    required: bool = True,
    options: list[str] | None = None,
) -> Field:
    return Field(
        key=field_key(label, ftype),
        label=label,
        type=ftype,  # type: ignore[arg-type]
        required=required,
        options=options,
    )


def _answer(field: Field, value: str, source: str = "profile") -> FieldAnswer:
    return FieldAnswer(field_key=field.key, value=value, source=source, confidence=1.0)


def _plan(
    answers: list[FieldAnswer],
    *,
    review_required: bool = False,
    missing: list[Field] | None = None,
) -> AnswerPlan:
    return AnswerPlan(
        answers=answers,
        missing_required=missing or [],
        review_required=review_required,
    )


def _opener(page: FakePage | Exception):
    """Page opener returning the fake page, or raising (failure injection)."""

    class _Cm:
        def __enter__(self) -> FakePage:
            if isinstance(page, Exception):
                raise page
            return page

        def __exit__(self, *exc: Any) -> None:
            return None

    return lambda url, headless, timeout: _Cm()


@pytest.fixture
def seam(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Route every external seam to a fake/tmp target."""
    monkeypatch.setattr(artifacts, "_data_dir", lambda: tmp_path)
    monkeypatch.setattr(artifacts, "_screenshots_enabled", lambda: False)
    monkeypatch.setattr(profile, "get_authoritative", lambda key, path=None: None)
    return {"tmp": tmp_path}


def _install_plugin(monkeypatch: pytest.MonkeyPatch, plugin: FakePlugin) -> None:
    monkeypatch.setattr(filler, "plugin_for", lambda url: plugin)


# --- fill() ---------------------------------------------------------------


class TestFill:
    def test_fill_applies_ops_per_type(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        fields = [
            _field("Full name", "text"),
            _field("Why fit", "textarea"),
            _field("Start date", "date", required=False),
            _field("Veteran status", "select", options=["Yes", "No"]),
            _field("Remote ok", "radio", options=["Yes", "No"]),
            _field("Agree to terms", "checkbox"),
            _field("Languages", "checkbox-group", options=["Python", "Go", "Rust"]),
        ]
        by_label: dict[str, FakeControl | None] = {
            "Full name": (name := FakeControl()),
            "Why fit": (why := FakeControl()),
            "Start date": (start := FakeControl()),
            "Veteran status": (vet := FakeControl()),
            "Agree to terms": (agree := FakeControl()),
        }
        by_role = {
            ("radio", "Yes"): (radio_yes := FakeControl()),
            ("checkbox", "Python"): (py := FakeControl()),
            ("checkbox", "Go"): (go := FakeControl()),
        }
        page = FakePage(by_label=by_label, by_role=by_role)
        plugin = FakePlugin()
        _install_plugin(monkeypatch, plugin)
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: fields)

        plan = _plan([
            _answer(fields[0], "Taylor Wong"),
            _answer(fields[1], "I ship fast"),
            _answer(fields[2], "2025-01-15"),
            _answer(fields[3], "No"),
            _answer(fields[4], "Yes"),
            _answer(fields[5], "yes"),
            _answer(fields[6], "Python|Go"),
        ])
        form = filler.fill(
            "https://jobs.ashbyhq.com/acme/123", plan, "app-1",
            page_opener=_opener(page), applications_path=tmp_path / "apps.csv",
        )

        assert name.ops == [("fill", "Taylor Wong")]
        assert why.ops == [("fill", "I ship fast")]
        assert start.ops == [("fill", "2025-01-15")]
        assert vet.ops == [("select_option", "No")]
        assert radio_yes.ops == [("check", None)]
        assert agree.ops == [("check", None)]
        assert py.ops == [("check", None)] and go.ops == [("check", None)]
        assert plugin.pre_extract_calls == 1 and len(plugin.post_fill_calls) == 1
        assert all(f.answer for f in form.fields)

        store = applications_store(tmp_path / "apps.csv")
        row = store.get("app-1")
        assert row is not None
        assert row.status == "ready_to_submit"
        assert len(row.fields_json) == len(fields)
        assert all(f["submitted"] is False for f in row.fields_json)
        assert row.status_history_json[0].status == "ready_to_submit"
        assert "app-1" in row.screenshot_dir

    def test_fill_review_required_gates_to_needs_review(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        field = _field("Sponsorship needed?", "text")
        page = FakePage(by_label={"Sponsorship needed?": FakeControl()})
        _install_plugin(monkeypatch, FakePlugin())
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [field])

        plan = _plan([], review_required=True, missing=[field])
        filler.fill(
            "https://x/1", plan, "app-2", page_opener=_opener(page),
            applications_path=tmp_path / "apps.csv",
        )
        row = applications_store(tmp_path / "apps.csv").get("app-2")
        assert row is not None and row.status == "needs_review"

    def test_fill_unfillable_required_field_forces_needs_review(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        field = _field("Ghost field", "text")
        page = FakePage(by_label={})  # no control for the label
        _install_plugin(monkeypatch, FakePlugin())
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [field])

        plan = _plan([_answer(field, "anything")])  # plan says ready, DOM disagrees
        filler.fill(
            "https://x/2", plan, "app-3", page_opener=_opener(page),
            applications_path=tmp_path / "apps.csv",
        )
        row = applications_store(tmp_path / "apps.csv").get("app-3")
        assert row is not None and row.status == "needs_review"

    def test_fill_file_uses_resume_path_fallback(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            profile, "get_authoritative", lambda key, path=None: "data/taylor.pdf"
        )
        field = _field("Resume", "file")
        page = FakePage(by_label={})  # label missing → raw selector fallback
        file_control = FakeControl()
        page.raw_locators['input[type="file"]'] = file_control
        _install_plugin(monkeypatch, FakePlugin())
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [field])

        # No plan answer for the upload; resume path comes from the profile.
        plan = _plan([])
        filler.fill(
            "https://x/3", plan, "app-4", page_opener=_opener(page),
            applications_path=tmp_path / "apps.csv",
        )
        assert file_control.ops == [("set_input_files", "data/taylor.pdf")]

    def test_fill_unknown_field_type_skipped(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        field = _field("Mystery", "unknown")
        page = FakePage()
        _install_plugin(monkeypatch, FakePlugin())
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [field])

        plan = _plan([_answer(field, "??", source="llm_draft")])
        form = filler.fill(
            "https://x/4", plan, "app-5", page_opener=_opener(page),
            applications_path=tmp_path / "apps.csv",
        )
        assert form.fields[0].answer is None  # never fabricated


# --- submit() -------------------------------------------------------------


def _persist_row(
    tmp_path: Path,
    app_id: str,
    status: str = "ready_to_submit",
    fields: list[dict[str, Any]] | None = None,
) -> Path:
    csv = tmp_path / "apps.csv"
    row = ApplicationsRow(
        id=app_id,
        job_url="https://jobs.ashbyhq.com/acme/123",
        ats_type="ashby",
        status=status,
        fields_json=fields or [],
        status_history_json=[
            StatusEvent(status=status, source="filler", at=datetime.now(UTC))
        ],
        created_at=datetime.now(UTC),
    )
    applications_store(csv).append(row)
    return csv


class TestSubmit:
    def test_refuses_when_not_ready(self, tmp_path: Path) -> None:
        csv = _persist_row(tmp_path, "app-r", status="needs_review")
        with pytest.raises(SubmissionError):
            filler.submit("app-r", applications_path=csv)

    def test_unknown_id_raises(self, tmp_path: Path) -> None:
        csv = tmp_path / "apps.csv"
        with pytest.raises(SubmissionError):
            filler.submit("nope", applications_path=csv)

    def test_submit_success_marks_row(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        field = _field("Full name", "text")
        fk = field.model_dump()
        fk["answer"] = "Taylor W. (edited)"  # reviewer edit persisted pre-submit
        csv = _persist_row(tmp_path, "app-s", fields=[fk])

        name = FakeControl()
        page = FakePage(by_label={"Full name": name})
        plugin = FakePlugin()
        _install_plugin(monkeypatch, plugin)
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [field])

        updated = filler.submit(
            "app-s", page_opener=_opener(page), applications_path=csv
        )

        assert name.ops == [("fill", "Taylor W. (edited)")]
        assert plugin.submit_control.ops == [("click", None)]
        assert "networkidle" in page.load_states
        assert updated.status == "submitted"
        assert updated.submitted_at is not None
        assert updated.fields_json[0]["submitted"] is True

        store = applications_store(csv)
        persisted = store.get("app-s")
        assert persisted is not None
        assert persisted.status == "submitted"
        assert persisted.status_history_json[-1].status == "submitted"

    def test_escalates_to_browserbase_on_local_failure(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BROWSERBASE_API_KEY", "test-key")
        csv = _persist_row(tmp_path, "app-e", fields=[_field("A", "text").model_dump() | {"answer": "x"}])

        local_page = FakePage(by_label={"A": FakeControl()})
        bb_page = FakePage(by_label={"A": FakeControl()})
        _install_plugin(monkeypatch, FakePlugin())
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [_field("A", "text")])

        updated = filler.submit(
            "app-e",
            page_opener=_opener(TimeoutError("playwright timeout")),
            browserbase_opener=_opener(bb_page),
            applications_path=csv,
        )
        assert updated.status == "submitted"

    def test_all_attempts_fail_marks_failed_and_raises(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BROWSERBASE_API_KEY", "test-key")
        csv = _persist_row(tmp_path, "app-f")
        _install_plugin(monkeypatch, FakePlugin())
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [])

        with pytest.raises(SubmissionError):
            filler.submit(
                "app-f",
                page_opener=_opener(RuntimeError("captcha")),
                browserbase_opener=_opener(RuntimeError("bb also down")),
                applications_path=csv,
            )
        row = applications_store(csv).get("app-f")
        assert row is not None and row.status == "failed"
        assert "bb also down" in row.status_history_json[-1].raw_snippet

    def test_error_banner_after_click_fails(
        self, monkeypatch: pytest.MonkeyPatch, seam: dict[str, Any], tmp_path: Path
    ) -> None:
        csv = _persist_row(tmp_path, "app-b")
        page = FakePage(content="<html>something went wrong</html>")
        _install_plugin(monkeypatch, FakePlugin())
        monkeypatch.setattr(filler, "discover_fields", lambda p, pl: [])

        with pytest.raises(SubmissionError):
            filler.submit("app-b", page_opener=_opener(page), applications_path=csv)
        row = applications_store(csv).get("app-b")
        assert row is not None and row.status == "failed"

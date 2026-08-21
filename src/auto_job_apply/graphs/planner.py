"""Answer-planning graph: ApplicationForm + applicant profile -> AnswerPlan.

LangGraph pipeline (``load_form`` -> ``try_profile`` -> ``draft_llm`` ->
``resolve_missing`` -> END). Each field is answered from the authoritative
profile/self-learning store first; fields still unanswered that are required
or short-answer (textarea) get an LLM draft. Required fields with no answer
surface in ``missing_required`` and force ``review_required`` — the planner
never fabricates required answers when the LLM cannot produce one.

The LLM is reachable only through ``services.llm`` (OpenRouter + Langfuse
tracing). Tests inject a fake drafter via ``plan_answers(..., drafter=...)``
so no network calls happen in unit tests.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from auto_job_apply.logging import logger
from auto_job_apply.prompts.planner import build_field_prompt, page_context
from auto_job_apply.services import learning, profile
from auto_job_apply.services.extractor import ApplicationForm, Field


class FieldAnswer(BaseModel):
    """One resolved answer for one form field."""

    field_key: str
    value: str
    source: Literal["profile", "llm_draft"]
    confidence: float


class AnswerPlan(BaseModel):
    """Planner output consumed by the filler-submitter leaf."""

    answers: list[FieldAnswer]
    missing_required: list[Field]
    review_required: bool


class FieldDraft(BaseModel):
    """Structured LLM output for a single field draft."""

    value: str
    confidence: float = 0.5


Drafter = Callable[[Field, str], "FieldDraft | None"]


class _PlannerState(TypedDict, total=False):
    form: ApplicationForm
    page_text: str | None
    drafter: Drafter
    answers: dict[str, FieldAnswer]
    missing_required: list[Field]
    review_required: bool


def _load_form(state: _PlannerState) -> dict[str, Any]:
    form = state["form"]
    logger.info(
        "planner: loaded form url=%s ats=%s fields=%d",
        form.url,
        form.ats_type,
        len(form.fields),
    )
    return {"answers": {}}


def _try_profile(state: _PlannerState) -> dict[str, Any]:
    """Answer fields from the authoritative profile/self-learning store."""
    answers: dict[str, FieldAnswer] = dict(state.get("answers", {}))
    for field in state["form"].fields:
        if field.key in answers:
            continue
        try:
            hit = learning.suggest(field.label)
        except Exception:  # noqa: BLE001 — profile lookup must degrade like drafting
            logger.warning("planner: profile lookup failed for %r", field.label)
            hit = None
        if hit:
            answers[field.key] = FieldAnswer(
                field_key=field.key, value=hit, source="profile", confidence=1.0
            )
    logger.info(
        "planner: profile answered %d/%d fields",
        len(answers),
        len(state["form"].fields),
    )
    return {"answers": answers}


def _default_drafter(field: Field, prompt: str) -> FieldDraft | None:
    """LLM draft via services.llm (OpenRouter + Langfuse). Never raises."""
    from auto_job_apply.services import llm as llm_service

    try:
        model = llm_service.get_llm(role="planner")
        runnable = llm_service.structured(model, FieldDraft)
        result = runnable.invoke(prompt)
        draft = (
            result
            if isinstance(result, FieldDraft)
            else FieldDraft.model_validate(result)
        )
        return draft if draft.value.strip() else None
    except Exception as exc:  # noqa: BLE001 — drafting must degrade to missing
        logger.warning("planner: LLM draft failed for %r: %s", field.label, exc)
        return None


def _draft_llm(state: _PlannerState) -> dict[str, Any]:
    """Draft answers with the LLM for unanswered required/short-answer fields."""
    form = state["form"]
    answers: dict[str, FieldAnswer] = dict(state.get("answers", {}))
    drafter = state.get("drafter") or _default_drafter

    org, role = page_context(form.url, state.get("page_text"))
    profile_answers = {row.question_key: row.answer for row in profile.all() if row.answer}
    full_name = profile.get_authoritative("full_name") or ""

    drafted = 0
    for field in form.fields:
        if field.key in answers:
            continue
        if not (field.required or field.type == "textarea"):
            continue  # optional non-short-answer fields stay blank for review
        prompt = build_field_prompt(
            label=field.label,
            ftype=field.type,
            required=field.required,
            options=field.options,
            profile_answers=profile_answers,
            org=org,
            role=role,
            full_name=full_name,
        )
        draft = drafter(field, prompt)
        if draft is None:
            continue
        answers[field.key] = FieldAnswer(
            field_key=field.key,
            value=draft.value,
            source="llm_draft",
            confidence=draft.confidence,
        )
        drafted += 1
    logger.info("planner: LLM drafted %d answers", drafted)
    return {"answers": answers}


def _resolve_missing(state: _PlannerState) -> dict[str, Any]:
    answers = state.get("answers", {})
    missing = [
        f for f in state["form"].fields if f.required and f.key not in answers
    ]
    if missing:
        logger.warning(
            "planner: %d required fields unanswered: %s",
            len(missing),
            [f.label for f in missing],
        )
    return {"missing_required": missing, "review_required": bool(missing)}


def _build_graph() -> Any:
    graph = StateGraph(_PlannerState)
    graph.add_node("load_form", _load_form)
    graph.add_node("try_profile", _try_profile)
    graph.add_node("draft_llm", _draft_llm)
    graph.add_node("resolve_missing", _resolve_missing)
    graph.add_edge(START, "load_form")
    graph.add_edge("load_form", "try_profile")
    graph.add_edge("try_profile", "draft_llm")
    graph.add_edge("draft_llm", "resolve_missing")
    graph.add_edge("resolve_missing", END)
    return graph.compile()


_GRAPH = _build_graph()


def plan_answers(
    form: ApplicationForm,
    *,
    page_text: str | None = None,
    drafter: Drafter | None = None,
) -> AnswerPlan:
    """Run the planner graph over an extracted form.

    ``page_text`` is the extractor's snapshot HTML (optional; used only to
    scrape role/org context for short-answer drafts). ``drafter`` overrides
    the LLM drafting call — the test seam.
    """
    state: _PlannerState = {"form": form, "page_text": page_text}
    if drafter is not None:
        state["drafter"] = drafter
    result = _GRAPH.invoke(state)
    return AnswerPlan(
        answers=list(result.get("answers", {}).values()),
        missing_required=result.get("missing_required", []),
        review_required=result.get("review_required", False),
    )


__all__ = ["AnswerPlan", "FieldAnswer", "FieldDraft", "plan_answers"]

# Answer Planner
- **Status:** Defined
- **Parent:** [application-filling index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Turn an `ApplicationForm` + applicant profile into an `AnswerPlan`: each field answered (from profile or LLM draft) or marked missing; required-missing fields surfaced.

## Design & Implementation Spec
**File:** `src/auto_job_apply/graphs/planner.py` (LangGraph), prompt templates in `src/auto_job_apply/prompts/planner.py`.
- For each `Field`: consult `services/learning.suggest(label)` (authoritative only); else if required or short-answer: LLM structured call with prompt packing field label, options, profile-all, job page text (from snapshot HTML), and a clause for startup/role/culture context used in short-answer generation.
- Output `AnswerPlan { answers: list[FieldAnswer], missing_required: list[Field], review_required: bool }`; `FieldAnswer { field_key, value, source: profile|llm_draft, confidence: float }`.
- `missing_required` nonempty → `review_required=True`, status bumped by filler leaf.
- LangGraph nodes: `load_form` → `try_profile` → `draft_llm` → `resolve_missing` → END; every LLM call traced (Langfuse via `services/llm`).
- Edge: `extract(url)` may time out partially — planner still attempts found fields.

## Dependencies
- [./field-extractor-IN_REVIEW.md](./field-extractor-IN_REVIEW.md),
- [../applicant-profile/profile-csv-IN_REVIEW.md](../applicant-profile/profile-csv-IN_REVIEW.md),
- [../applicant-profile/self-learning-store-IN_REVIEW.md](../applicant-profile/self-learning-store-IN_REVIEW.md),
- [../shared-infra/llm-openrouter-IN_REVIEW.md](../shared-infra/llm-openrouter-IN_REVIEW.md).

## Acceptance Criteria
- Given profile answers for seed keys and LLM available, all answerable required fields get values; unanswerable → `missing_required` with label.
- Short answers embed at least: role title + org name (scraped from page) + profile `full_name`.

## Test Plan & Definition of Done
- Unit with mocked LLM: profile-hit short-circuit, missing-LLM→missing list, graph shape. `tests/test_planner.py` green.

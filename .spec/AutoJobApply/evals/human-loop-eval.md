# Human-Loop Eval
- **Status:** Defined
- **Parent:** [evals index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Prove the fail-safe loop end-to-end: a required field the system cannot answer forces human review; the evaluating harness supplies the answer through the review API; the system completes successfully on re-submission — including the progressive-disclosure variant where the field only appears after a rejected first submit.

## Design & Implementation Spec
**File:** `evals/run_evals.py` (new `human_loop` case runner), `tests/test_human_loop_eval.py`.

**Scenario A (unknown-at-fill):** a mock case with a required field whose label is absent from profile + aliases and not LLM-answerable (e.g. an obscure token question). Assert: fill → `needs_review`; harness patches the value via `PATCH /applications/{id}/fields`; `POST /confirm` → `ready_to_submit`; `POST /submit` → success; recorded submission contains **exactly the human-supplied value** for that field; `learning.suggest(label)` now returns the human value (self-learning write-back verified).

**Scenario B (progressive disclosure):** the `ashby/progressive` case from [./mock-sites-confirmation-IN_REVIEW.md](./mock-sites-confirmation-IN_REVIEW.md). Assert: first submit → `REJECTED_VALIDATION` with the missing field named; harness re-extracts (new field present), patches via review API, confirms, re-submits → `CONFIRMED`; submission contains the new field's human value.

**Scoring:** both scenarios are pass/fail booleans added to the eval results JSON (`human_loop: {scenario_a: bool, scenario_b: bool}`); overall gate unchanged (required_completion) but these print in the summary.

## Dependencies
- [./mock-sites-confirmation-IN_REVIEW.md](./mock-sites-confirmation-IN_REVIEW.md)
- [../application-filling/confirmation-detection.md](../application-filling/confirmation-detection.md)
- [../application-filling/review-api-cli-COMPLETED.md](../application-filling/review-api-cli-COMPLETED.md)

## Acceptance Criteria
- Scenario A: needs_review → human patch → submit success with exact value; self-learning verified.
- Scenario B: rejection naming the field → re-extract → patch → re-submit confirmed.

## Test Plan & Definition of Done
- Runs inside `evals/run_evals.py`; `uv run pytest tests/test_human_loop_eval.py -q` green (mocked transport); full eval gate green.

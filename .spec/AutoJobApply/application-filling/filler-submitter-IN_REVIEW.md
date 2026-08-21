# Filler & Submitter
- **Status:** Defined
- **Parent:** [application-filling index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Playwright-driven deterministic fill of the form, artifact capture, gate to review; and the actual `submit` action triggered only from review.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/filler.py`
- `fill(url, plan: AnswerPlan, application_id) -> ApplicationForm`:
  - Per field type, map to Playwright op: text/textarea→fill, select→select_option (or custom select fallback per plugin), radio/checkbox→check, date→fill/format, file→set_input_files from `resume_path`, short answers → fill.
  - Write `applications.csv` row: `id, job_url, ats_type, status, fields_json, status_history_json, created_at, submitted_at, screenshot_dir`.
  - If plan.review_required → `status="needs_review"`, else `status="ready_to_submit"`. `fields_json.submitted=False`.
  - Capture artifacts per field + full page via `artifacts.snapshot_page` (last image/hyperlinks embedded in detail view later).
- `submit(application_id)` (only called by review-api-cli):
  - Re-walk the form privately, inject **only authoritative answers** and `plan` values with `source in {profile, llm_draft}` that the reviewer approved.
  - Click plugin `submit_button(page)`; post-submit extraction of confirmation; on success mark rows `status="submitted"`, `submitted_at` set; on failure `status="failed"`, error captured in `SubmissionError`.
  - Browserbase escalation: on `Playwright timeout/captcha/bot`, if `BROWSERBASE_API_KEY` present, retry through Browserbase session.

## Dependencies
- [./answer-planner-IN_REVIEW.md](./answer-planner-IN_REVIEW.md),
- [../shared-infra/errors-artifacts-IN_REVIEW.md](../shared-infra/errors-artifacts-IN_REVIEW.md),
- (through planner) all upstream deps.

## Acceptance Criteria
- Missing-required-fields → `needs_review` and NOT submitted; all-required-answered → `ready_to_submit`.
- After `submit`, on success `status="submitted"` and artifacts contain screenshot(s) with file input honored.

## Test Plan & Definition of Done
- Unit with mocked plan; integration against eval mocks in eval-runner. `tests/test_filler.py` green.

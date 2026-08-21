# Application Filling
- **Status:** Defined
- **Parent:** [AutoJobApply master spec](../index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Purpose & Scope
Given a job URL on Ashby, Greenhouse, or Lever: extract the form, draft answers from the applicant profile + LLM, fill the form deterministically, capture screenshots, and gate submission behind the review policy. URLs for any other ATS are put on hold (`status=on_hold`).

## Design Decisions Specific to This Subsystem
- Plugin per ATS under `application-filling/ats-plugins/`; plugins own selectors/quirks only — extraction/planning/submission logic is shared.
- `applications.csv` rows carry `fields_json` (list of extracted+answered fields) and `status_history_json`.
- Required fields with no confident answer are never guessed; the application goes to `needs_review`.
- Submission runs through the review API/CLI so a human (or the verifying agent) confirms first.

## Children
- [ats-registry](./ats-registry-IN_REVIEW.md) — URL → ATS detection + plugin lookup
- [ats-plugins/](./ats-plugins/index.md) — per-ATS plugin contract + the three plugins
- [field-extractor](./field-extractor-IN_REVIEW.md) — Playwright walk, iterative field discovery, `ApplicationForm` model
- [answer-planner](./answer-planner-IN_REVIEW.md) — profile lookup + LLM drafts → `AnswerPlan`
- [filler-submitter](./filler-submitter-IN_REVIEW.md) — deterministic fill + artifacts + review gate
- [review-api-cli](./review-api-cli-IN_REVIEW.md) — FastAPI review routes + CLI + submit action

## Dependencies
- [shared-infra/config-surface](../shared-infra/config-surface-IN_REVIEW.md)
- [shared-infra/csv-store](../shared-infra/csv-store-IN_REVIEW.md)
- [shared-infra/errors-artifacts](../shared-infra/errors-artifacts-IN_REVIEW.md)
- [shared-infra/llm-openrouter](../shared-infra/llm-openrouter-IN_REVIEW.md)
- [applicant-profile/profile-csv](../applicant-profile/profile-csv-IN_REVIEW.md)
- [applicant-profile/self-learning-store](../applicant-profile/self-learning-store-IN_REVIEW.md)

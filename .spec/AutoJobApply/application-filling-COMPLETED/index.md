# Application Filling
- **Status:** Defined
- **Parent:** [AutoJobApply master spec](../index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Purpose & Scope
Given a job URL on Ashby, Greenhouse, or Lever: extract the form, draft answers from the applicant profile + LLM, fill the form deterministically, capture screenshots, and gate submission behind the review policy. URLs for any other ATS are put on hold (`status=on_hold`).

## Design Decisions Specific to This Subsystem
- Plugin per ATS under `application-filling-COMPLETED/ats-plugins-COMPLETED/`; plugins own selectors/quirks only — extraction/planning/submission logic is shared.
- `applications.csv` rows carry `fields_json` (list of extracted+answered fields) and `status_history_json`.
- Required fields with no confident answer are never guessed; the application goes to `needs_review`.
- Submission runs through the review API/CLI so a human (or the verifying agent) confirms first.

## Children
- [ats-registry](./ats-registry-COMPLETED.md) — URL → ATS detection + plugin lookup
- [ats-plugins-COMPLETED/](./ats-plugins-COMPLETED/index.md) — per-ATS plugin contract + the three plugins
- [field-extractor](./field-extractor-COMPLETED.md) — Playwright walk, iterative field discovery, `ApplicationForm` model
- [answer-planner](./answer-planner-COMPLETED.md) — profile lookup + LLM drafts → `AnswerPlan`
- [filler-submitter](./filler-submitter-COMPLETED.md) — deterministic fill + artifacts + review gate
- [review-api-cli](./review-api-cli-COMPLETED.md) — FastAPI review routes + CLI + submit action

## Dependencies
- [shared-infra-COMPLETED/config-surface](../shared-infra-COMPLETED/config-surface-COMPLETED.md)
- [shared-infra-COMPLETED/csv-store](../shared-infra-COMPLETED/csv-store-COMPLETED.md)
- [shared-infra-COMPLETED/errors-artifacts](../shared-infra-COMPLETED/errors-artifacts-COMPLETED.md)
- [shared-infra-COMPLETED/llm-openrouter](../shared-infra-COMPLETED/llm-openrouter-COMPLETED.md)
- [applicant-profile-COMPLETED/profile-csv](../applicant-profile-COMPLETED/profile-csv-COMPLETED.md)
- [applicant-profile-COMPLETED/self-learning-store](../applicant-profile-COMPLETED/self-learning-store-COMPLETED.md)

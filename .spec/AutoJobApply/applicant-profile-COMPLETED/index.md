# Applicant Profile
- **Status:** Defined
- **Parent:** [AutoJobApply master spec](../index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Purpose & Scope
The applicant's canonical answer store: name, email, resume path, and self-learned demographic/screening answers (veteran, disability, visa, etc.). Feeds the answer planner and absorbs user edits so repeat questions auto-answer over time.

## Design Decisions Specific to This Subsystem
- Key-value rows (`question_key, answer, source, updated_at`) — not a wide schema — so new question types never need a file shape change.
- `source` is one of `manual | learned | llm_draft`; only `manual | learned` are authoritative for auto-answer.
- Question canonicalization (label → stable `question_key`) is deterministic-first, LLM-second, and only the planner writes authoritative rows through the self-learning store.

## Children
- [profile-csv](./profile-csv-COMPLETED.md) — `applicant_profile.csv` model + CRUD service
- [self-learning-store](./self-learning-store-COMPLETED.md) — canonicalization + write-back of edited/confirmed answers

## Dependencies
- [shared-infra-COMPLETED/csv-store](../shared-infra-COMPLETED/csv-store-COMPLETED.md)
- [shared-infra-COMPLETED/llm-openrouter](../shared-infra-COMPLETED/llm-openrouter-COMPLETED.md)

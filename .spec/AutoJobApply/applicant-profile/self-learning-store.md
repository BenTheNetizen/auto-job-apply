# Self-Learning Store
- **Status:** Defined
- **Parent:** [applicant-profile index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Map free-form form quirks ("Are you a protected veteran?", "Visa sponsorship needed?", "Gender identity") to canonical `profile` keys; learn from user edits so future runs auto-answer.

## Design & Implementation Spec
**Service:** `src/auto_job_apply/services/learning.py`
- `canonicalize(label: str) -> str | None`:
  1. Deterministic: lowercase→strip punctuation→collapse whitespace; look up alias table (`src/auto_job_apply/services/learning_aliases.json`), e.g. `"veteran_status"` ← `["veteran", "protected veteran", ...]`.
  2. LLM fallback via `services/llm.structured(...)` when alias lookup misses; suggestion reviewed (per acceptance) before becoming authoritative.
- `learn(label, answer, source="learned")` writes into `applicant_profile.csv` via `services/profile`.
- `suggest(label)` returns authoritative answer if one exists.

## Dependencies
- [./profile-csv.md](./profile-csv.md)
- [../shared-infra/llm-openrouter.md](../shared-infra/llm-openrouter.md)

## Acceptance Criteria
- Alias hits never call the LLM.
- LLM canonicalization writes `source=llm_draft` only; elevation to `learned` happens via review UI or explicit call.
- Aliases file committed; case-insensitive lookup.

## Test Plan & Definition of Done
- Unit: alias hit, alias miss→LLM path mocked, persistence to profile. `tests/test_learning.py` green.

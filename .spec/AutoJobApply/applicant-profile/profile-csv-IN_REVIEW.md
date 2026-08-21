# Profile CSV
- **Status:** Defined
- **Parent:** [applicant-profile index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
The authoritative key-value store for the applicant's answers: `applicant_profile.csv`.

## Design & Implementation Spec
**Service:** `src/auto_job_apply/services/profile.py`
**Row model (`ApplicantProfileRow`)**: `question_key: str`, `answer: str`, `source: Literal["manual","learned","llm_draft"]`, `updated_at: datetime`.
**Built-in seed keys** (always present; empty until user sets): `full_name`, `email` (mock: `taylor.wong@agentmail.to` in evals), `resume_path` (default `data/Benjamin Chen Resume.pdf`), `phone`, `linkedin_url`, `github_url`, `website`.
**API:** `get(key) -> str | None`, `set(key, answer, source)`, `all() -> list[Row]`, `get_authoritative(key)` (manual/learned only).
File is created on first use under `${DATA.dir}/applicant_profile.csv`.

## Dependencies
- [../shared-infra/csv-store-IN_REVIEW.md](../shared-infra/csv-store-IN_REVIEW.md) — must be COMPLETED before claiming.

## Acceptance Criteria
- `set` then `get` round-trips; `get_authoritative` ignores `llm_draft` rows.
- File created under `DATA.dir` at first touch; built-in seed rows present with empty answers.

## Test Plan & Definition of Done
- Unit: CRUD, authoritative filter, seed rows exist, source enum honored. `tests/test_profile_csv.py` green.

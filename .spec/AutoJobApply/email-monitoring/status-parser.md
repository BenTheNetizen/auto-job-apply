# Status Parser
- **Status:** Defined
- **Parent:** [email-monitoring index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Classify a recruiter email into application status with confidence, first deterministic then LLM.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/status_parser.py`
- Enum `ApplicationStatus`: `acknowledged|rejected|interview_scheduled|assessment|offer|withdrawn|unknown`.
- `parse(subject, body) -> ParsedStatus { status, confidence, raw_snippet }`:
  1. Deterministic rules (regex/wordlist; e.g. "rejected", "we'd like to interview", "offer letter").
  2. If rules miss or confidence <0.8: LLM structured output `services/llm.structured(...)`, prompt asks for enum with brief snippet.
  3. Always return `raw_snippet` (max ~600 chars) for embedding in status history.
- Pure function; no I/O.

## Dependencies
- [../shared-infra/llm-openrouter-IN_REVIEW.md](../shared-infra/llm-openrouter-IN_REVIEW.md)

## Acceptance Criteria
- Rules handle ≥85% of seeded fixture emails; LLM path covered by mocked call on edge cases.

## Test Plan & Definition of Done
- Fixtures in `tests/fixtures/emails/*.txt` + expected enum; mocked LLM path; `tests/test_status_parser.py` green.

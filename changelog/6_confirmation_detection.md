# Confirmation detection (leaf)

- `services/confirmation.py`: `SubmissionConfirmation` enum (CONFIRMED / REJECTED_VALIDATION / REJECTED_BOT / UNKNOWN) + `confirm_by` composition helper (redirect → toast → validation → bot → UNKNOWN, ~5s poll window).
- All three ATS plugins implement `confirm_submission(page)` with their own redirect/toast/validation selectors; generic text fallbacks cover mismatches.
- Filler `_submit_once` returns the verdict; `submit()` marks REJECTED_* rows failed and raises `SubmissionError` (post-click non-retryable, no Browserbase escalation); UNKNOWN still submits with a logged warning; verdict recorded in status history `raw_snippet`.
- Removed the old `_CONFIRM_TEXT`/`_await_confirmation` page scan.
- 25 new tests in `tests/test_confirmation.py`; FakePlugin/StubPlugin stubs updated; full suite 317 green.

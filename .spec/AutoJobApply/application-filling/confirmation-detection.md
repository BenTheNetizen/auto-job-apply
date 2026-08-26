# Confirmation Detection
- **Status:** Defined
- **Parent:** [application-filling index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Replace the generic `_CONFIRM_TEXT` scan with per-ATS, machine-checkable submission confirmation: `SubmissionConfirmation` enum + plugin method, handling both toast-style and redirect-style success signals.

## Design & Implementation Spec
**Files:** `src/auto_job_apply/services/ats/{ashby,greenhouse,lever}.py` (add method), `src/auto_job_apply/services/filler.py` (wire in), `src/auto_job_apply/services/ats_registry.py` (extend protocol), `tests/test_confirmation.py`.

**Enum** (new, in `services/filler.py` or `errors.py`-adjacent module `services/confirmation.py`):
```python
class SubmissionConfirmation(str, Enum):
    CONFIRMED = "confirmed"                  # definitive success signal
    REJECTED_VALIDATION = "rejected_validation"  # server rejected field format/missing
    REJECTED_BOT = "rejected_bot"            # bot-detection / captcha / generic block
    UNKNOWN = "unknown"                      # no signal either way
```

**Plugin protocol addition:** `confirm_submission(page) -> SubmissionConfirmation`
- Each plugin checks, in order: (1) **redirect-style** — URL changed to a confirmation/thanks path (ashby: `/application-submitted` or `?submitted`; lever: `/thanks`; greenhouse: confirmation view), (2) **toast-style** — ATS-specific success banner selector, (3) **validation-rejection** — ATS-specific error summary/field-error markers (e.g. greenhouse `.field-error`, ashby error list), (4) **bot signals** — captcha iframe, "verify you are human", Cloudflare challenge, HTTP 403 block page, (5) else `UNKNOWN`.
- Timeout-bounded: each check is a short poll loop (~5s max total) since toasts render async.

**Filler wiring:** `_submit_once` calls `plugin.confirm_submission(page)` after click (replacing `_await_confirmation`'s text scan; keep the error-banner raise as one input to `REJECTED_VALIDATION`). Result is stored on the application row's status history as a `StatusEvent` with `source="filler"` and the enum value in `raw_snippet`. `REJECTED_VALIDATION`/`REJECTED_BOT` → row `status="failed"` with context; `UNKNOWN` → `status="submitted"` but log warning (never block a real click on an ambiguous signal); `CONFIRMED` → `status="submitted"`.

## Dependencies
- [./filler-submitter-COMPLETED.md](./filler-submitter-COMPLETED.md)

## Acceptance Criteria
- Against eval mocks: toast-style case → `CONFIRMED`; redirect-style case → `CONFIRMED`; field-rejection case → `REJECTED_VALIDATION`; bot-detection case → `REJECTED_BOT`.
- Row status history contains the enum outcome after every submit attempt.
- Post-click failures remain non-retryable (no double-submit).

## Test Plan & Definition of Done
- Unit tests with fake pages per signal path per ATS (≥12 cases). `uv run pytest tests/test_confirmation.py -q` green; full suite green.

# Email Confirmation Wait
- **Status:** Defined
- **Parent:** [email-monitoring index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
After a successful submit, wait for the employer's confirmation email with a bounded timeout and record the outcome as a first-class enum.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/email_confirmation.py`, `tests/test_email_confirmation.py`, config keys in `config/settings.json`.

**Enum:**
```python
class EmailConfirmationStatus(str, Enum):
    RECEIVED = "received"      # confirmation-classified email arrived in time
    TIMEOUT = "timeout"        # no confirmation email within the window
    NOT_CHECKED = "not_checked"  # waiting disabled by config
```

**Config:** `EMAIL.confirmation_timeout_seconds` (default `600` = 10 min), `EMAIL.confirmation_poll_seconds` (default `30`), `EMAIL.confirmation_wait_enabled` (default `true`).

**Service:** `wait_for_confirmation(application_id, *, timeout_seconds=None) -> EmailConfirmationStatus`
- Polls the AgentMail inbox (reuses `email_monitor`'s client + `match_application` + `status_parser`) every `confirmation_poll_seconds` until timeout.
- A match whose parsed status is `acknowledged` (or stronger: interview/assessment/offer) → `RECEIVED`; append `StatusEvent(source="email", status="confirmation_received")` and return.
- Timeout → append `StatusEvent(source="email", status="confirmation_timeout")` and return `TIMEOUT`. Never raises.
- Wired as an optional post-submit step: `filler.submit(..., wait_for_email=False)` default False for sync callers; the CLI `review submit --wait-email` flag and eval runner opt in.

## Dependencies
- [./agentmail-poll-COMPLETED.md](./agentmail-poll-COMPLETED.md)
- [../application-filling/filler-submitter-COMPLETED.md](../application-filling/filler-submitter-COMPLETED.md)

## Acceptance Criteria
- With a stubbed client delivering a matching ack email on poll N: returns `RECEIVED` and history event written.
- With no matching email: returns `TIMEOUT` after the (test-shortened) window; history event written.
- Disabled config → `NOT_CHECKED`, no polling.

## Test Plan & Definition of Done
- Unit tests with stubbed AgentMail client (short timeouts). `uv run pytest tests/test_email_confirmation.py -q` green; full suite green.

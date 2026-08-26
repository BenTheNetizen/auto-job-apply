# Live Email E2E
- **Status:** Defined
- **Parent:** [evals index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Close the loop with a real inbox: mock submission sends a real confirmation email via AgentMail to `auto-apply-test@agentmail.to`; the eval runs the live poll and asserts the full pipeline (receive → parse → status update → mark-read).

## Design & Implementation Spec
**Files:** `evals/mock-sites/vite.config.js` (submit-recorder sends email), `evals/mock-sites/email.js` (sender helper), `evals/run_evals.py` (new case type), `tests/test_live_email.py` (skipped without key).

**Mock sender:** on successful `POST /submit` for cases flagged `sends_email: true` in gold, the dev server sends a real email via AgentMail REST (`POST https://api.agentmail.to/v0/inboxes/{sender}/messages/send` with `AGENTMAIL_API_KEY` from env) — from a mock employer inbox (create `noreply-hiring@agentmail.to` if absent) **to `auto-apply-test@agentmail.to`**, subject `Application received — <job title>`, body containing the org name + an acknowledgement phrase matching `status_parser`'s `acknowledged` rules.

**Eval wiring:** eval profile fixture email = `auto-apply-test@agentmail.to` for these cases. After submit: run `email_monitor.poll_once()` against the **live** inbox (stubbed client replaced by real SDK); assert (a) row's `status_history_json` gained an `acknowledged` event, (b) message marked read, (c) replay ledger recorded. Then `wait_for_confirmation(..., timeout_seconds=60)` returns `RECEIVED` (or already-RECEIVED short-circuit).

**Safety:** inbox `auto-apply-test@agentmail.to` ONLY — never the personal `benjaminchen@agentmail.to`. Skip gracefully when `AGENTMAIL_API_KEY` absent.

## Dependencies
- [./mock-sites-confirmation-IN_REVIEW.md](./mock-sites-confirmation-IN_REVIEW.md)
- [../email-monitoring/email-confirmation-wait-IN_REVIEW.md](../email-monitoring/email-confirmation-wait-IN_REVIEW.md)

## Acceptance Criteria
- End-to-end run: submit on a `sends_email` case → real email lands in `auto-apply-test@agentmail.to` → live `poll_once` updates the application row + marks read → `wait_for_confirmation` = `RECEIVED`.
- Negative control: a case with `sends_email: false` → `wait_for_confirmation(timeout=30)` = `TIMEOUT`.

## Test Plan & Definition of Done
- Manual verified run logged in changelog; `tests/test_live_email.py` skips without key.

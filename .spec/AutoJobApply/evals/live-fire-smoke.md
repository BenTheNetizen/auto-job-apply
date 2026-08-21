# Live-Fire Smoke (Stretch)
- **Status:** Defined
- **Parent:** [evals index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Optional: validate end-to-end against one real Ashby, Greenhouse, or Lever posting under Browserbase with the mock identity — flag bot detection early, capture eventual DOM drift the mocks can't predict.

## Design & Implementation Spec
**File:** `evals/live_fire.py`
- Requires `BROWSERBASE_API_KEY`; user-supplied target URL; never submits — extract, fill (mock identity), screenshot, and exit before clicking submit. Then manual user review decides real submission.
- Uses `services/filler.fill` + plugin paths; Browserbase session via `browserbase` SDK connected to Playwright chromium-over-cdp.
- Documents observed bot-detection signals into `evals/live_fire_notes.md` (captcha, rate limit, JS challenge).

## Dependencies
- [./eval-runner.md](./eval-runner.md) — signals only after mocks pass at 100%.

## Acceptance Criteria
- From one real URL: extraction ≥90% fields found end-to-end with Browserbase; no submission occurs; screenshots recorded.

## Test Plan & Definition of Done
- Manual run, recorded in the changelog (`changelog/<n>_live_fire_smoke.md`).

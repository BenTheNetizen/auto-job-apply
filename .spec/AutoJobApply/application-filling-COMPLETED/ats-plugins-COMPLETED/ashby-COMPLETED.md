# Ashby Plugin
- **Status:** Defined
- **Parent:** [ats-plugins index](./index.md)
- **Root:** [AutoJobApply master spec](../../index.md)

## Goal
Ashby-specific selectors + quirks.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/ats/ashby.py`
- `detect(url)`: host endswith `ashbyhq.com`.
- `base_selectors`: form root `form`, label strategy `label:has-text(...)`, required marked by `*` in label or `[required]` attr; selects via `select`, checkboxes/radios via `input[type=checkbox|radio]`, file upload `input[type=file]`.
- `pre_extract`: dismiss Ashby cookie banner if present (`button:has-text("Accept")`).
- `submit_button`: `button[type=submit]` with text `Submit Application|Submit`.
- Quirks documented inline; selectors prefer role/text over brittle ids.

## Dependencies
- [../ats-registry-COMPLETED.md](../ats-registry-COMPLETED.md)

## Acceptance Criteria
- Registry returns this plugin for `https://jobs.ashbyhq.com/<org>/<id>`.
- `submit_button` returns a visible locator against eval mock `/ashby` route.

## Test Plan & Definition of Done
- Unit: detect matrix. Integration (eval-runner): selector presence verified. `tests/test_ats_ashby.py` green.

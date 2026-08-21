# Greenhouse Plugin
- **Status:** Defined
- **Parent:** [ats-plugins index](./index.md)
- **Root:** [AutoJobApply master spec](../../index.md)

## Goal
Greenhouse-specific selectors + quirks.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/ats/greenhouse.py`
- `detect(url)`: host endswith `boards.greenhouse.io`.
- `base_selectors`: fields in `#application form`, required marked by `span.asterisk` or `[required]`; quiz/demographic sections under `fieldset`; selects include custom `select2` containers (fallback: treat `<select>` hidden behind select2 as a select).
- `pre_extract`: cookie modal dismissal if present; expand `.expand_all` sections when present.
- `submit_button`: `input[type=submit]` or `button` with `Submit` text.
- Document any select2 shadow-DOM strategy as fallback only.

## Dependencies
- [../ats-registry.md](../ats-registry.md)

## Acceptance Criteria
- Registry routes `https://boards.greenhouse.io/<org>/<id>` here.
- Handles both plain and select2-backed `<select>`s on eval mocks.

## Test Plan & Definition of Done
- Unit: detect matrix. Integration via eval-runner. `tests/test_ats_greenhouse.py` green.

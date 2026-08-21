# Lever Plugin
- **Status:** Defined
- **Parent:** [ats-plugins index](./index.md)
- **Root:** [AutoJobApply master spec](../../index.md)

## Goal
Lever-specific selectors + quirks.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/ats/lever.py`
- `detect(url)`: host endswith `jobs.lever.co`.
- `base_selectors`: form usually under `div.application-form` or `form`; required marked by `*` adjacent to label; questions grouped under accordion sections — `pre_extract` clicks `.toggle` headers to expose fields before extraction.
- `submit_button`: `button`/`input[type=submit]` with `Submit` text.
- Document accordion and dynamic-reveal quirks inline.

## Dependencies
- [../ats-registry-COMPLETED.md](../ats-registry-COMPLETED.md)

## Acceptance Criteria
- Registry routes `https://jobs.lever.co/<org>/<id>` here.
- Accordion-style sections are un-collapsed before extraction on eval mocks.

## Test Plan & Definition of Done
- Unit: detect matrix. Integration via eval-runner. `tests/test_ats_lever.py` green.

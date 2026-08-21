# ATS Registry
- **Status:** Defined
- **Parent:** [application-filling index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Map a job URL to its ATS plugin, and define the plugin contract the three implementations satisfy.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/ats_registry.py`
- `ATSType = Literal["ashby","greenhouse","lever"]`; else `UnsupportedATSError`.
- Host patterns (also public-info endpoints if needed later):
  - ashby → `ashbyhq.com`, `jobs.ashbyhq.com`
  - greenhouse → `boards.greenhouse.io`
  - lever → `jobs.lever.co`
- `ATSPlugin` Protocol (typing.Protocol): `name`, `detect(url) -> bool`, `base_selectors() -> dict[str,str]`, `submit_button(page) -> Locator`, `pre_extract(page) -> None` (expand/cookies/etc.), `post_fill(page, answers) -> None`.
- `registry()` returns singleton list of plugin singletons.

## Dependencies
- [../shared-infra-COMPLETED/errors-artifacts-COMPLETED.md](../shared-infra-COMPLETED/errors-artifacts-COMPLETED.md)

## Acceptance Criteria
- Known host → plugin; unknown host → `UnsupportedATSError` with the URL in `.context`.
- Plugins register themselves at import via `registry()`; adding a new ATS = one file.

## Test Plan & Definition of Done
- Unit: detection matrix incl. negative, unknown → error with context. `tests/test_ats_registry.py` green.

# Errors & Artifacts
- **Status:** Defined
- **Parent:** [shared-infra index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Shared error taxonomy and the artifact writer for screenshots/HTML/error dumps.

## Design & Implementation Spec
**Errors** — `src/auto_job_apply/errors.py`:
- Keep `AutoJobApplyError` base. Add: `UnsupportedATSError(url)`, `ExtractionError`, `PlannerError`, `SubmissionError(fields_missing)`, `EmailPollError`, `ConfigError`.
- Each error carries a machine-usable `.context: dict` so callers can stash partial form state.

**Artifacts** — `src/auto_job_apply/utils/artifacts.py`:
- `artifact_dir(application_id) -> Path`: creates `${DATA.dir}/artifacts/<application_id>/`.
- `write_artifact(application_id, name, bytes|str) -> Path` (suffixes by mimetype).
- `snapshot_page(application_id, page, prefix) -> list[Path]`: Playwright screenshot + `page.content()` HTML dump; honors `FILLER.screenshots`.
- Artifacts must be path-safe (ids validated `[A-Za-z0-9-]+`).

## Dependencies
- None (engine-only; uses stdlib + Playwright types).

## Acceptance Criteria
- New error classes importable in one line; `.context` dict survives `raise`/`str()`.
- `snapshot_page` writes both PNG and HTML to the per-application folder and returns paths.

## Test Plan & Definition of Done
- Unit: error context, artifact naming, path-safe validation, screenshots disabled-flag honored. `tests/test_errors_artifacts.py` green.

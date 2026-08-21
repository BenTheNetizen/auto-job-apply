# Evals
- **Status:** Defined
- **Parent:** [AutoJobApply master spec](../index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Purpose & Scope
Prove field-completion fidelity without touching the internet: static mock Ashby/Greenhouse/Lever apps (one React app) with gold-labeled expected submissions, a Langfuse-scored eval runner, and a stretch live-fire smoke path through Browserbase.

## Design Decisions Specific to This Subsystem
- Mock DOM structure mirrors each ATS's real application form closely enough that the per-ATS selectors are exercised; every field flavor (text, textarea, select, radio, checkbox group, date, file upload, short-answer) appears in at least one case.
- Gold labels store both required/optional-ness and expected answer mapping from a fixed mock profile.
- Eval metric: required-field completion rate (headline) + answer fidelity (exact/normalized match vs gold).

## Children
- [mock-sites](./mock-sites-IN_REVIEW.md) — React app with `/ashby`, `/greenhouse`, `/lever` routes + gold labels
- [eval-runner](./eval-runner.md) — run filler against mocks, score, publish Langfuse dataset run
- [live-fire-smoke](./live-fire-smoke.md) — stretch: real posting via Browserbase with mock identity

## Dependencies
- [application-filling/filler-submitter](../application-filling/filler-submitter-IN_REVIEW.md)
- [application-filling/review-api-cli](../application-filling/review-api-cli.md)
- [shared-infra/langfuse-tracing](../shared-infra/langfuse-tracing-IN_REVIEW.md)

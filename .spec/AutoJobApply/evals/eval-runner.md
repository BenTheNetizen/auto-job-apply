# Eval Runner
- **Status:** Defined
- **Parent:** [evals index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Run the real filler against the mock sites, score required-field completion and answer fidelity vs gold labels, and publish Langfuse-scored runs.

## Design & Implementation Spec
**File:** `evals/run_evals.py` (+ `evals/mock-sites/` app)
- Seeds a fresh `applicant_profile.csv` from `evals/fixtures/mock_profile.csv` (Taylor Wong identity) in a temp `DATA.dir`.
- For each case: `fill(url, ...)` real filler → `review-api` endpoints (agent-as-human) to confirm → `submit` → collect recorded payload from mock.
- Scoring per case: `required_completion = answered_required/gold_required_total` (target 1.0), `answer_fidelity = normalized exact match fraction` (normalize case/whitespace; date ISO; choices case-insensitive); per-ATS and overall aggregates.
- Langfuse: `score_eval(run_name=..., item_id=case, metric=required_completion, value=...)`; creates a dataset run name timestamped `eval-<iso>`.
- Exit code non-zero if overall `required_completion < 1.0` — this is the hill-climb gate.

## Dependencies
- [./mock-sites-IN_REVIEW.md](./mock-sites-IN_REVIEW.md),
- [../application-filling/filler-submitter.md](../application-filling/filler-submitter.md),
- [../application-filling/review-api-cli.md](../application-filling/review-api-cli.md),
- [../shared-infra/langfuse-tracing.md](../shared-infra/langfuse-tracing.md).

## Acceptance Criteria
- `uv run evals/run_evals.py` runs end-to-end, writes `evals/results/<timestamp>.json`, exits 0 when 100% on all cases, and Langfuse shows the run + scores (env present) or skips gracefully (env absent).

## Test Plan & Definition of Done
- Runs green locally; results JSON verified; headless via `FILLER.headless` default true.

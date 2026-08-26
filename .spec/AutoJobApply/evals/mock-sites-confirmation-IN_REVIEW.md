# Mock Sites — Confirmation Variants & Negative Cases
- **Status:** Defined
- **Parent:** [evals index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Extend the mock sites with realistic confirmation styles and failure modes so confirmation-detection and the human-loop can be evaluated deterministically.

## Design & Implementation Spec
**Files:** `evals/mock-sites/src/*.jsx`, `evals/mock-sites/vite.config.js` (submit-recorder gains response modes), `evals/mock-sites/gold/*.json`, `evals/mock_sites_gold.py`.

**New cases (≥1 per ATS where applicable):**
1. **Toast-style confirmation** — existing inline-result behavior becomes an explicit toast banner with ATS-shaped success text (`application submitted`/`thank you`). Cases: `ashby/basic` (keep), plus `greenhouse/toast`, `lever/toast`.
2. **Redirect-style confirmation** — after POST, page navigates to `/<ats>/<case>/confirmation` route rendering a confirmation view. Cases: `ashby/redirect`, `greenhouse/redirect`, `lever/redirect`.
3. **Validation rejection** — `POST /submit` with a malformed value (e.g. date not ISO on a designated field) returns **422** with `{error: "..."}`; page renders an ATS-shaped error summary/toast. Case: `greenhouse/reject-format` (server checks `start_date` matches `YYYY-MM-DD`), `ashby/reject-format`.
4. **Bot detection** — a case whose `/submit` returns **403** with a generic block page ("verify you are human"). Case: `lever/bot-detect`.
5. **Progressive field (re-submission)** — `POST /submit` first attempt returns **422** `{error, missing_field}`; the page then re-renders with an **additional required field** that was not in the initial form; a corrected second POST succeeds. Case: `ashby/progressive`. The new field must NOT be in the gold `applicant_profile` fixture (forces the human-loop).

**Server modes:** submit-recorder reads per-case behavior from `gold/<case>.json` → new optional keys: `confirmation_style: "toast"|"redirect"`, `reject_rules: [{field, pattern, error}]`, `bot_block: bool`, `progressive_field: {key, label, type, required, options}`.

## Dependencies
- [./mock-sites-COMPLETED.md](./mock-sites-COMPLETED.md)

## Acceptance Criteria
- All new routes render; `/submit` behaves per case config (200/422/403 verified by curl).
- Progressive case: first POST 422s and names the missing field; form re-render includes it; second POST 200s.
- Gold JSON updated for every new case with expected outcomes.

## Test Plan & Definition of Done
- `tests/test_mock_sites_gold.py` extended for new cases/keys; smoke via eval-runner harness.

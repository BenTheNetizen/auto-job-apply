# Mock Sites
- **Status:** Defined
- **Parent:** [evals index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
A single Vite + React app under `evals/mock-sites/` serving `/ashby`, `/greenhouse`, `/lever` routes that mimic each ATS's form DOM closely enough to exercise the real plugins — with gold labels for scoring.

## Design & Implementation Spec
- Routes: `/ashby/:case`, `/greenhouse/:case`, `/lever/:case`, each rendering the ATS-shaped DOM (form root selectors, required markers, upload inputs, accordion where applicable).
- Cases: ≥3 per ATS; case catalog covers text, textarea, select, radio, checkbox group, date, file, short-answer; one case per ATS has annoying select2-ish or accordion behavior.
  - Greenhouse case includes select2-backed `<select>`.
  - Lever case includes accordion reveal.
- `POST` to `/submit` records JSON payload (`{applicationId, fields}`); gold labels live in `evals/mock-sites/gold/<case>.json` with full expected field set + expected answers given a mock `applicant_profile.csv` (mock identity: Taylor Wong <taylor.wong@agentmail.to>).
- Deterministically serves at `${EVALS.mock_base_url}` (default `http://localhost:5173`).

## Dependencies
- None.

## Acceptance Criteria
- `npm run dev --prefix evals/mock-sites` serves all three routes; ATS plugins `detect()` recognize each route URL; `/submit` accepts POSTed JSON.
- Gold JSON files exist for ≥9 cases covering the flavor matrix.

## Test Plan & Definition of Done
- Smoke test run by eval-runner: all routes 200; gold JSON parses into pydantic models in Python side. Verified via [./eval-runner.md](./eval-runner.md).

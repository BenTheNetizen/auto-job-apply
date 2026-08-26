# Review API + CLI
- **Status:** Defined
- **Parent:** [application-filling index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Human/agent review surface over `applications.csv`: list, inspect, edit fields (marked required/optional), confirm, and trigger `submit`.

## Design & Implementation Spec
**Routes** add onto existing `server` in `src/auto_job_apply/server.py`:
- `GET /applications` (list w/ status filter)
- `GET /applications/{id}` (detail + artifacts paths)
- `PATCH /applications/{id}/fields` body `{field_key, value}`; edits write back to `fields_json` and mark `learning.learn(label,value)` for demographic-like flips (threshold-free via `services/learning`).
- `POST /applications/{id}/confirm` moves `needs_review` → `ready_to_submit` if zero required blanks; body optional `{learn_from_edits: bool}`.
- `POST /applications/{id}/submit` → `filler.submit(id)`.
**CLI** `python -m auto_job_apply.cli` (commands: `review list|show|edit|confirm|submit`, and `fill <url>` one-shot chaining extract→plan→fill) using the API when server running, else direct services.
- Edit→learn hook only writes canonicalized label + value and `source=learned` when value non-empty.

## Dependencies
- [./filler-submitter-COMPLETED.md](./filler-submitter-COMPLETED.md),
- [../applicant-profile-COMPLETED/self-learning-store-COMPLETED.md](../applicant-profile-COMPLETED/self-learning-store-COMPLETED.md).

## Acceptance Criteria
- All 5 routes on `server` return shapes above (status filter honored); CLI works in both modes.
- Edit-then-submit round trip: edited value appears in final submission payload (integration test with eval mocks).

## Test Plan & Definition of Done
- API tests with `httpx AsyncClient` on `server`; CLI with click runner. Integration via eval-runner. `tests/test_review_api.py` green.

# Replay Safety
- **Status:** Defined
- **Parent:** [email-monitoring index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Guarantee a message is never replayed even if the poll loop crashes mid-way.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/replay_ledger.py`
- CSV `processed_messages.csv` via `csv_store`: `message_id, processed_at, application_id (nullable), status (nullable)`.
- `is_processed(message_id) -> bool`; `record(message_id, application_id, status)`.
- Authoritative: record AFTER the status update lands in `applications.csv`; order designed so message replay on crash is conservative (status update again → dedupe at message-id level, otherwise replay-tolerate).

## Dependencies
- [../shared-infra/csv-store.md](../shared-infra/csv-store.md)

## Acceptance Criteria
- `is_processed→record→is_processed` flips False→True; ledger survives concurrent writers via filelock.

## Test Plan & Definition of Done
- Unit: first-process→dupe-skip; crash-safe order test simulated. `tests/test_replay_ledger.py` green.

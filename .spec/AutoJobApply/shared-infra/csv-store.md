# CSV Store
- **Status:** Defined
- **Parent:** [shared-infra index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
The one Pydantic-backed CSV persistence engine every subsystem uses.

## Design & Implementation Spec
**File:** `src/auto_job_apply/utils/csv_store.py`, row models per subsystem (they import this engine).

**Engine (`CsvStore[T: BaseModel]`)**:
- `CsvStore(path, model)` — header ordered from `model.model_fields`; JSON-in-column fields supported via `model_dump(mode="json")` per cell.
- `read_all() -> list[T]`, `append(row)`, `update(id, row)`, `get(id)`, `upsert(key_field, row)`, `append_event(row, list_field, event)`.
- Atomic writes: write `${file}.tmp`, `os.replace`.
- Cross-process safety: `filelock` (add dependency `filelock`) guarding each write.
- Optional columns tolerate missing keys on load (schema evolution: add column → old files load with defaults).
- All datetime stored ISO-8601 UTC.

**Concurrency:** engine is synchronous; subsystem services decide the loop. Engine never holds the lock across calls into LLM/Playwright code.

## Dependencies
- None.

## Acceptance Criteria
- Round-trip a BaseModel with a `list[...]` of another BaseModel through JSON-in-column (mimics `fields_json`).
- Header order stable and matches `model_fields` order; schema evolution tolerant.
- `filelock` prevents interleaved writes from two processes.

## Test Plan & Definition of Done
- Unit: round-trip nested models, schema evolution, atomic rename, lock behavior. `tests/test_csv_store.py` green.
- Verified via downstream `(applicant-profile|application-filling|email-monitoring)` leaves.

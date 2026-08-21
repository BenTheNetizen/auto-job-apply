# Field Extractor
- **Status:** Defined
- **Parent:** [application-filling index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Walk a live form in Playwright and emit a normalized `ApplicationForm` with every field, its required-ness, and stable identity.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/extractor.py`
- `Field` model: `key` (stable hash of label+type), `label`, `type: Literal["text","textarea","select","radio","checkbox","checkbox-group","date","file","unknown"]`, `required: bool`, `options: list[str] | None`, `answer: str | None`, `submitted: bool`.
- `extract(url) -> ApplicationForm`:
  1. `registry().detect(url)` → get plugin.
  2. Headed/headless per `FILLER.headless`; viewport captured; `pre_extract(page)`.
  3. **Iterative discovery loop:** after each `Field` extraction, re-query form in case answering/shifting focus reveals new fields. Snapshot per iteration via `artifacts.snapshot_page`.
  4. Normalized fallback: where plugin selectors miss, generic label-driven discovery finds text/textarea/select etc.
- `ApplicationForm { url, ats_type, fields: list[Field], discovered_iterations: int }`; rejected→`UnsupportedATSError` upstream.
- Timeout: hard cap `FILLER.timeout_ms`; partial forms saved via `ExtractionError(context={"partial": form})`.

## Dependencies
- [./ats-registry.md](./ats-registry.md)
- [./ats-plugins/ashby.md](./ats-plugins/ashby.md), [./ats-plugins/greenhouse.md](./ats-plugins/greenhouse.md), [./ats-plugins/lever.md](./ats-plugins/lever.md)
- [../shared-infra/errors-artifacts-IN_REVIEW.md](../shared-infra/errors-artifacts-IN_REVIEW.md)

## Acceptance Criteria
- Against eval mocks: extracts ≥9/10 known flavors; labels and `required` flags match gold labels.
- On timeout/exception: partial form still lands in `ExtractionError.context["partial"]` with ≥1 field or snapshots exist.

## Test Plan & Definition of Done
- Unit: `Field` stable-key hash, fallback selector path, partial-form path. Integration: against eval mocks (harness in evals/eval-runner). `tests/test_extractor.py` green.

# LLM OpenRouter Client
- **Status:** Defined
- **Parent:** [shared-infra index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
The single entry point for LLM calls, with structured output, token/cost logging, and Langfuse tracing baked in.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/llm.py`
- `get_llm(role: str = "default") -> ChatOpenAI` — `base_url=https://openrouter.ai/api/v1`, api key from `OPENROUTER_API_KEY` env, model from `settings.LLM.model` (or `settings.LLM.<role>_model` override), temperature `LLM.temperature`.
- Attaches `[langfuse_handler]` in `config["callbacks"]` automatically (from `services/langfuse_service.get_callback_handler()`).
- `structured(model, schema) -> Runnable` — `with_structured_output(schema)`; falls back to prompt+parse if provider rejects response_format.
- Logging: log tokens/cost from `response.usage`/`response_metadata`.

## Dependencies
- [./langfuse-tracing-COMPLETED.md](./langfuse-tracing-COMPLETED.md)

## Acceptance Criteria
- Every downstream subsystem calls `get_llm`/`structured` — no direct `ChatOpenAI` construction elsewhere.
- Model override per role works via nested env `AUTO_JOB_APPLY_LLM__PLANNER_MODEL=...`.
- When Langfuse envs are present, traces appear in the UI; when absent, no crash.

## Test Plan & Definition of Done
- Unit: model defaults, role override, structured-output fallback path (mock provider rejection), callback attachment. `tests/test_llm.py` green.
- Verified: one live OpenRouter ping via `uv run python -c "from auto_job_apply.services.llm import get_llm; print(get_llm().invoke('ping').content[:20])"`.

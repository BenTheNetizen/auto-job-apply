# Langfuse Tracing
- **Status:** Defined
- **Parent:** [shared-infra index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
One Langfuse factory that everything else consumes: LLM calls, LangGraph runs, and eval scores.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/langfuse_service.py`
- Import-safe when `LANGFUSE_*` envs are absent (returns no-op factories; logs once).
- `get_client() -> Langfuse | None`, `get_callback_handler() -> CallbackHandler | None` compatible with LangChain/LangGraph `config["callbacks"]`.
- `score_eval(run_name, item_id, metric, value, comment)` for evals/.
- `flush()` on graceful exit; `.env` auto-loaded (see config-surface).
- Reads `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` from env.

## Dependencies
- Nothing but env (no dependency on `config-surface` to keep the cycle zero; env-only here).

## Acceptance Criteria
- `get_callback_handler()` returns a handler usable by `ChatOpenAI` when envs present; no-op otherwise.
- `score_eval` posts scores that show up in the Langfuse UI (verified manually with the account's project).

## Test Plan & Definition of Done
- Unit, envs mocked: absent → no-op, present → client constructed with right base URL. `tests/test_langfuse_service.py` green.
- Verified once with real envs after `eval-runner` lands.

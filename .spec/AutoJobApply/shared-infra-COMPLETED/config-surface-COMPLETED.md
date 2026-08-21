# Config Surface
- **Status:** Defined
- **Parent:** [shared-infra index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
One well-typed configuration surface for the whole system: schema, defaults, env wiring, startup validation.

## Design & Implementation Spec
**File:** `src/auto_job_apply/config.py` (extend existing), `config/settings.json` (commit), `config/settings.local.json` (gitignored, secrets).

**Settings schema (Dynaconf, `envvar_prefix="AUTO_JOB_APPLY"`):**
- `DATA.dir` (default `"data"`) — CSV + artifact root.
- `LLM.model` (default `"openai/gpt-4.1-mini"`), `LLM.temperature` (default `0`), `LLM.planner_model` optional override — OpenRouter ids.
- `FILLER.headless` (default `true`), `FILLER.timeout_ms` (default `45000`), `FILLER.screenshots` (default `true`).
- `EMAIL.poll_interval_seconds` (default `300`), `EMAIL.account` (default `"taylor.wong@agentmail.to"`).
- `API.host/port/cors` (existing template keys keep working).
- `EVALS.mock_base_url` (default `"http://localhost:5173"`).

**Env → local settings:** `.env` at repo root is loaded (`load_dotenv=True` already). Document in `config/settings.local.json.example`: `OPENROUTER_API_KEY`, `BROWSERBASE_API_KEY`, `AGENTMAIL_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` read from process env by consumers — settings module exposes `settings.get(...)` only; secrets NEVER land in `settings.json`.

**Behavior:** on import, validate `DATA.dir` exists (create if missing) and warn (not raise) when required env keys are absent for the subsystems actually in use. Startup validation lives behind `validate(busy_flag)` no-op seams so tests can import safely.

## Dependencies
- None.

## Acceptance Criteria
- `from auto_job_apply.config import settings` exposes every key above with defaults; changing e.g. `LLM.model` in `settings.local.json` is reflected at runtime.
- `AUTO_JOB_APPLY_LLM__MODEL=...` env override works (nested `__` separator per Dynaconf).
- Missing `DATA.dir` is created on import; missing secrets warn without breaking import.

## Test Plan & Definition of Done
- Unit tests (`tests/test_config.py`): defaults, env-nesting override, data-dir creation, warn-only on missing secrets. `uv run pytest tests/test_config.py` green.
- Verified: `uv run python -c "from auto_job_apply.config import settings; print(settings.to_dict())"` works with/without `.env`.

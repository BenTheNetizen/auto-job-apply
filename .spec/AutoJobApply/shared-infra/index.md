# Shared Infra
- **Status:** Defined
- **Parent:** [AutoJobApply master spec](../index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Purpose & Scope
Cross-cutting plumbing every subsystem depends on: Dynaconf config schema, the Pydantic-backed CSV persistence engine, the OpenRouter LLM client, Langfuse tracing, and the error/artifact utilities.

## Design Decisions Specific to This Subsystem
- One CSV engine for all files; domain row models live in their owning subsystems, engine lives here.
- All LLM calls route through the OpenRouter client — no subsystem constructs its own model.
- Langfuse handler factory is created here; LangGraph/LangChain code in `src/auto_job_apply/graphs/` receives it via config.

## Children
- [config-surface](./config-surface.md) — settings.json schema + env wiring + validation
- [errors-artifacts](./errors-artifacts.md) — error taxonomy + artifact (screenshot/HTML) writer
- [csv-store](./csv-store.md) — generic Pydantic-row CSV engine
- [langfuse-tracing](./langfuse-tracing.md) — client init + callback factory + flush
- [llm-openrouter](./llm-openrouter.md) — chat client, structured output helper, usage logging

## Dependencies
- None (this subsystem is the base of the DAG).

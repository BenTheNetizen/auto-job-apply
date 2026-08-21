# Email Monitoring
- **Status:** Defined
- **Parent:** [AutoJobApply master spec](../index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Purpose & Scope
Poll the AgentMail inbox (`taylor.wong@agentmail.to` in all verification; never the personal address) for inbound recruiter mail, classify the application status, append to `applications.csv` status history, and mark messages read with replay safety.

## Design Decisions Specific to This Subsystem
- Poll via AgentMail SDK on a configurable interval; the per-message handler is shaped exactly like a webhook handler (`handle_message(message)`) so a webhook swap later changes transport only.
- Match inbound mail to an application row in priority order: explicit application id in thread metadata → sender domain/subject match → job-title match. Unmatched mail is logged, never silently discarded.
- Dedupe on `message_id` via a processed-ledger CSV; crashes mid-loop must not reprocess updates.

## Children
- [status-parser](./status-parser.md) — email → `{status, confidence, raw_snippet}` (rules first, LLM fallback)
- [replay-safety](./replay-safety.md) — processed-message ledger
- [agentmail-poll](./agentmail-poll.md) — poll loop, match, update, mark-read

## Dependencies
- [shared-infra/config-surface](../shared-infra/config-surface.md)
- [shared-infra/llm-openrouter](../shared-infra/llm-openrouter.md)
- [shared-infra/csv-store](../shared-infra/csv-store.md)
- [shared-infra/errors-artifacts](../shared-infra/errors-artifacts.md)

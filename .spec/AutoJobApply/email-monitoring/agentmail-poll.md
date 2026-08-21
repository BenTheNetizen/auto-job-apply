# AgentMail Poll
- **Status:** Defined
- **Parent:** [email-monitoring index](./index.md)
- **Root:** [AutoJobApply master spec](../index.md)

## Goal
Poll AgentMail on schedule → match → parse → update → mark-read, with the handler shaped as a webhook for future swap.

## Design & Implementation Spec
**File:** `src/auto_job_apply/services/email_monitor.py`; entry point `python -m auto_job_apply.cli email-monitor [--once]`.
- Uses AgentMail Python SDK (dependency `agentmail`) with `AGENTMAIL_API_KEY` env; account from `EMAIL.account`.
- `poll_once()` loop:
  1. List unread messages.
  2. For each: `handle_message(msg)` first tries application-id match in thread metadata, then sender/subject match (domain → org), then job-title substring match; unmatched logs warn, skip without marking read.
  3. `handle_message(msg)` — shaped exactly like a webhook handler: verify match → `status_parser.parse(subject, body)` → append status event in `applications.csv` (`status_history_json` + top-level `status`) → `replay_ledger.record` → mark-read.
- `email-monitor` subcommand also accepts `--interval` override.
- Errors from SDK/parse wrapped in `EmailPollError` with context; one bad message doesn't kill the loop.

## Dependencies
- [./status-parser.md](./status-parser.md),
- [./replay-safety.md](./replay-safety.md),
- [../shared-infra/errors-artifacts.md](../shared-infra/errors-artifacts.md),
- [../shared-infra/config-surface.md](../shared-infra/config-surface.md).

## Acceptance Criteria
- `--once` against mocked SDK: one unseen message updates exactly one application row, ledger + mark-read invoked, message not returned on next poll.
- Unmatched messages: warning logged but left unread (recycled next interval).

## Test Plan & Definition of Done
- Unit with a stubbed AgentMail client; integration uses agentmail MCP in dev-session. `tests/test_email_monitor.py` green.

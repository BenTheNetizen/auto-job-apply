# AutoJobApply — Master Spec
- **Status:** COMPLETED (all leaves verified; eval gate green at required_completion=1.0; live-fire-smoke deferred as stretch pending a real posting URL)
- **Parent:** none (this is the root)

## 1. Problem Statement & Motivation
Applying to jobs means clicking through many sites and answering the same questions repeatedly. v0 builds the two riskiest, highest-value subsystems end-to-end: **filling and submitting job applications** on Ashby/Greenhouse/Lever, and **monitoring email** (AgentMail) to track application statuses. Job discovery (preferences → startups → job links) is deferred until the fill pipeline is validated; for v0, job URLs arrive manually.

## 2. Context & Background
Repo: `auto-job-apply` (FastAPI template: `config`, `logging`, `server`, `db`, `errors`, `__main__`). Source brief: `my-spec.md`. Keys available in `~/.zshrc`: `OPENROUTER_API_KEY`, `BROWSERBASE_API_KEY`, `AGENTMAIL_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`. Resume lives at `data/Benjamin Chen Resume.pdf` (real data is **never** used in verification; mock identity `taylor.wong@agentmail.to`).

## 3. System Overview & Architecture
```
job URL (manual) ──► application-filling ──► applications.csv ──► review API/CLI ──► submit
                        │                          ▲
applicant_profile.csv ──┤ (answers, drafts)        │ status_history
                        │                          │
email (AgentMail) ──────► email-monitoring ────────┘
evals: mock Ashby/Greenhouse/Lever sites ──► filler ──► Langfuse eval scores
```
- Agents: LangChain/LangGraph per subsystem; model via OpenRouter; Langfuse tracing on every run.
- Persistence: CSV + Pydantic row models (Postgres/Supabase later, 1:1 table mapping).
- Config: Dynaconf (`src/auto_job_apply/config.py`); non-secret tuning in `config/settings.json`, secrets in `config/settings.local.json` or env.

## 4. Global Design Decisions (from Decision Log)
1. **Scope:** shared-infra, applicant-profile, application-filling, email-monitoring, evals. Dashboard excluded from this tree (thin FastAPI review API + CLI instead). Job discovery deferred entirely.
2. **Data:** `applicant_profile.csv` (key-value rows: `question_key, answer, source, updated_at`) + `applications.csv` (one row per application; `fields_json`, `status_history_json` embedded JSON columns). Pydantic per row; 1:1 future tables — no CSV→ORM fan-out mid-model; explicit migrations only.
3. **Submit policy:** any application missing required-field data → human review queue; **never fabricate** required answers. During build verification, the agent acts as the human via the review API/CLI.
4. **Fill strategy:** Playwright browser-first against the real form DOM; iterative field extraction (forms may reveal fields progressively); per-ATS selector plugins + generic DOM fallback; Browserbase only as escalation when bot-detection breaks local Playwright; submissions proxied through the local machine for now.
5. **Email:** scheduled AgentMail SDK poll → parse → status update → mark-read; the parse/update/match logic is a webhook-shaped service method so a future webhook swap is drop-in.
6. **Evals:** static mock Ashby/Greenhouse/Lever apps in one React app with gold labels; Langfuse eval runner scoring field-completion fidelity; live-fire smoke via Browserbase = stretch goal.
7. **Future Supabase move:** one table per CSV, thin persistence adapter, explicit migrations (`supabase migration new`), never `apply_migration` for iteration.

## 5. Dependency Map (leaf level)
- [shared-infra](./shared-infra-COMPLETED/index.md)
  - config-surface — depends on: none
  - errors-artifacts — depends on: config-surface
  - csv-store — depends on: config-surface
  - langfuse-tracing — depends on: config-surface
  - llm-openrouter — depends on: config-surface, langfuse-tracing
- [applicant-profile](./applicant-profile-COMPLETED/index.md)
  - profile-csv — depends on: csv-store
  - self-learning-store — depends on: profile-csv, llm-openrouter
- [application-filling](./application-filling/index.md)
  - ats-registry — depends on: errors-artifacts
  - ats-plugins-COMPLETED/ashby — depends on: ats-registry
  - ats-plugins-COMPLETED/greenhouse — depends on: ats-registry
  - ats-plugins-COMPLETED/lever — depends on: ats-registry
  - field-extractor — depends on: ats-registry + all three ats plugins, errors-artifacts
  - answer-planner — depends on: field-extractor, profile-csv, self-learning-store, llm-openrouter
  - filler-submitter — depends on: answer-planner, errors-artifacts
  - review-api-cli — depends on: filler-submitter, self-learning-store
- [email-monitoring](./email-monitoring/index.md)
  - status-parser — depends on: llm-openrouter
  - replay-safety — depends on: csv-store
  - agentmail-poll — depends on: status-parser, replay-safety, errors-artifacts
- [evals](./evals/index.md)
  - mock-sites — depends on: none
  - eval-runner — depends on: mock-sites, filler-submitter, review-api-cli, langfuse-tracing
  - live-fire-smoke — depends on: eval-runner (stretch; Browserbase)

## 6. Child Specs
- [shared-infra](./shared-infra-COMPLETED/index.md) — config surface, CSV engine, LLM/OpenRouter client, Langfuse tracing, errors/artifacts
- [applicant-profile](./applicant-profile-COMPLETED/index.md) — profile CSV + self-learning question→answer store
- [application-filling](./application-filling/index.md) — ATS registry/plugins, field extraction, answer planning, fill/submit, review API+CLI
- [email-monitoring](./email-monitoring/index.md) — AgentMail poll, status parsing, replay safety

## Open Questions
- Mock-eval React app tooling: Vite assumed; adjust in [evals/mock-sites](./evals/mock-sites-COMPLETED.md) if user prefers CRA/Next.
- Whether the email poll loop runs in-process with the API server or as `auto_job_apply email-monitor`: decided in [email-monitoring/agentmail-poll](./email-monitoring/agentmail-poll-COMPLETED.md) leaf (separate run command preferred).

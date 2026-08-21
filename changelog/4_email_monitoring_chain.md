# Email monitoring chain

Three leaves: status-parser (deterministic rules + LLM fallback via services/llm), replay-safety (processed_messages.csv ledger via CsvStore, idempotent upsert), agentmail-poll (AgentMail SDK poll_once/run_forever, webhook-shaped handle_message). Adds services/applications.py — shared applications.csv row model (filler-submitter imports/tightens it later). New dep: agentmail. CLI subcommand wiring deferred to review-api-cli leaf (email_monitor exposes poll_once/run_forever for it).

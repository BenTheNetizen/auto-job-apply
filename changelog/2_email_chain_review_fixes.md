# Email-chain review fixes

- applications.append_status: history append is now atomic via CsvStore.append_event (was a read-modify-write race on status_history_json); added update_top_level flag for history-only appends.
- status_parser: offer rule now requires the noun 'offer' ('pleased to extend an invitation to interview' no longer classifies as offer).
- email_monitor: LLM 'unknown' (confidence>0) appends a history event but no longer overwrites the row's top-level status; logged instead.

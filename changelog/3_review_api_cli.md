# 3 — Review API + CLI

- `services/review.py`: list/show/edit/confirm/submit seam over applications.csv; edits learn via `services/learning`; confirm enforces the never-fabricate gate (required blanks → 409).
- `server.py`: 5 review routes (GET list/detail, PATCH fields, POST confirm/submit); detail includes artifact paths.
- `cli.py`: `review list|show|edit|confirm|submit`, `fill <url>` (extract→plan→fill), `email-monitor [--once] [--interval N]`; uses HTTP API when the server is reachable, direct services otherwise.

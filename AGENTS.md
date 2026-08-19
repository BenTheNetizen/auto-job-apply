# Agent guide

Run `make setup` once after cloning so package and env-prefix placeholders are renamed. Do not leave `auto_job_apply` / `PKG` in a working project.

## Layout

- `src/<package>/` — library code (`config`, `logging`, `server`, `db`, `errors`, `__main__`)
- `config/settings.json` — committed defaults; `settings.local.json` — local overrides (gitignored via `*.local.json`)
- `scripts/setup.sh` — renames package + Dynaconf `envvar_prefix`
- `changelog/` — agent notes only: `{n}_{short_summary}.md` (e.g. `1_add_health_route.md`)

## Editing

- Config: read/write via `settings` from `<package>.config`. Nested env overrides use `__` (e.g. `PKG_API__PORT=9000`).
- HTTP: add routes on `server` in `<package>.server`; host/port/CORS come from `settings.API`.
- DB: use `engine` from `<package>.db` (`settings.DB.url` = Supabase Postgres URL).
- Errors: subclass `<Package>Error` from `<package>.errors`.
- Logging: import `logger` from `<package>.logging`.

## Run

```bash
uv sync
uv run <package>
```

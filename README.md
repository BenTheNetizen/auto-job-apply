# Python package template

uv-managed Python package with FastAPI, Dynaconf config, logging, and a Supabase-ready SQLAlchemy engine.

## Create a project from this template

**GitHub UI:** Use this template → Create a new repository

**CLI:**

```bash
gh repo create my-new-app --template BenTheNetizen/python-template --public --clone
cd my-new-app
```

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
make setup    # package name + env var prefix (e.g. my_app / MYAPP)
uv sync
uv run my_app
```

`setup` renames `auto_job_apply` everywhere and sets the Dynaconf `envvar_prefix`.

## Config

| File | Purpose |
|------|---------|
| `config/settings.json` | Committed defaults (`API`, `DB`) |
| `config/settings.local.json` | Local overrides (gitignored; copied from `.example` by setup) |

Env overrides use the prefix you chose, with `__` for nesting:

```bash
MYAPP_API__PORT=9000 uv run my_app
MYAPP_DB__URL=postgresql://... uv run my_app
```

## Useful commands

```bash
make help
make run           # after setup: uv run <package>
make docker-build
```

## Layout

```
src/<package>/     # config, logging, server, db, errors, __main__
config/            # settings.json (+ local overrides)
scripts/setup.sh   # one-time rename
changelog/         # agent change notes: {n}_{summary}.md
```

See [AGENTS.md](AGENTS.md) for editing guidance for coding agents.

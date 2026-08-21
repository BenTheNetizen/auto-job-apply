import logging
import os
from pathlib import Path
from typing import Iterable

from dynaconf import Dynaconf

logger = logging.getLogger("auto_job_apply.config")

settings = Dynaconf(
    settings_files=["config/settings.json", "config/settings.local.json"],
    environments=True,
    envvar_prefix="AUTO_JOB_APPLY",
    load_dotenv=True,
    dotenv_path=".env",
)

# Env keys each subsystem needs at runtime. Secrets live in the process env
# (or .env, loaded above) — NEVER in config/settings.json.
SUBSYSTEM_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "llm": ("OPENROUTER_API_KEY",),
    "browser": ("BROWSERBASE_API_KEY",),
    "email": ("AGENTMAIL_API_KEY",),
    "langfuse": (
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
    ),
}


def data_dir(path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the DATA.dir setting (CSV + artifact root)."""
    raw = path if path is not None else settings.get("DATA.dir", "data")
    return Path(raw)


def ensure_data_dir(path: str | os.PathLike[str] | None = None) -> Path:
    """Create DATA.dir if missing; returns the resolved path."""
    resolved = data_dir(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def missing_env_keys(subsystems: Iterable[str] | None = None) -> dict[str, list[str]]:
    """Env keys absent from the process env, grouped by subsystem.

    ``subsystems=None`` checks every known subsystem; pass a subset to check
    only the subsystems actually in use.
    """
    names = tuple(subsystems) if subsystems is not None else tuple(SUBSYSTEM_ENV_KEYS)
    return {
        name: [key for key in SUBSYSTEM_ENV_KEYS[name] if not os.environ.get(key)]
        for name in names
        if name in SUBSYSTEM_ENV_KEYS
    }


def validate(subsystems: Iterable[str] | None = None) -> dict[str, list[str]]:
    """Startup validation seam.

    Always import-safe: creates DATA.dir if missing and *warns* (never raises)
    about missing env keys. Returns the missing-key mapping so callers/tests
    can assert on it.
    """
    ensure_data_dir()
    missing = {k: v for k, v in missing_env_keys(subsystems).items() if v}
    if missing:
        flat = [key for keys in missing.values() for key in keys]
        logger.warning(
            "Missing env keys for subsystems %s: %s "
            "(set them in the environment or .env; never in settings.json)",
            ", ".join(sorted(missing)),
            ", ".join(flat),
        )
    return missing


# Import-time light validation: data dir exists; missing secrets warn only.
validate()

__all__ = [
    "settings",
    "SUBSYSTEM_ENV_KEYS",
    "data_dir",
    "ensure_data_dir",
    "missing_env_keys",
    "validate",
]

from dynaconf import Dynaconf

settings = Dynaconf(
    settings_files=["config/settings.json", "config/settings.local.json"],
    environments=True,
    envvar_prefix="AUTO_JOB_APPLY",
    load_dotenv=True,
    dotenv_path=".env",
)

__all__ = ["settings"]

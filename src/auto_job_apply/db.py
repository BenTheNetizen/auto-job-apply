from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from auto_job_apply.config import settings
from auto_job_apply.errors import AutoJobApplyError
from auto_job_apply.logging import logger

_db_url = settings.get("DB.url")

engine: Engine | None = None

if _db_url:
    engine = create_engine(_db_url, pool_pre_ping=True)
    logger.info("Database engine created")
else:
    logger.warning("DB.url is not set; database engine is unavailable")


def get_engine() -> Engine:
    if engine is None:
        raise AutoJobApplyError(
            "Database is not configured. Set DB.url in config or via env "
            "(e.g. AUTO_JOB_APPLY_DB__URL)."
        )
    return engine


__all__ = ["engine", "get_engine"]

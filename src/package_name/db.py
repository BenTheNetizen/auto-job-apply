from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from package_name.config import settings
from package_name.errors import PackageNameError
from package_name.logging import logger

_db_url = settings.get("DB.url")

engine: Engine | None = None

if _db_url:
    engine = create_engine(_db_url, pool_pre_ping=True)
    logger.info("Database engine created")
else:
    logger.warning("DB.url is not set; database engine is unavailable")


def get_engine() -> Engine:
    if engine is None:
        raise PackageNameError(
            "Database is not configured. Set DB.url in config or via env "
            "(e.g. PKG_DB__URL)."
        )
    return engine


__all__ = ["engine", "get_engine"]

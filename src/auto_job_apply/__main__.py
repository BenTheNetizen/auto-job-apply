import uvicorn

from auto_job_apply.config import settings
from auto_job_apply.logging import logger
from auto_job_apply.server import server


def main() -> None:
    host = settings.get("API.host", "0.0.0.0")
    port = int(settings.get("API.port", 8000))
    logger.info("Starting auto_job_apply on %s:%s", host, port)
    uvicorn.run(server, host=host, port=port)


if __name__ == "__main__":
    main()

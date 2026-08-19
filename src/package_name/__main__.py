import uvicorn

from package_name.config import settings
from package_name.logging import logger
from package_name.server import server


def main() -> None:
    host = settings.get("API.host", "0.0.0.0")
    port = int(settings.get("API.port", 8000))
    logger.info("Starting package_name on %s:%s", host, port)
    uvicorn.run(server, host=host, port=port)


if __name__ == "__main__":
    main()

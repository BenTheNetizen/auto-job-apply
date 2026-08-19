import logging

import colorlog

_handler = colorlog.StreamHandler()
_handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)s%(reset)s %(message)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
)

logger = logging.getLogger("package_name")
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(_handler)
logger.propagate = False

__all__ = ["logger"]

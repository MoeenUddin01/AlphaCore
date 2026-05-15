"""Centralised logging configuration for the Autonomous Crypto Quant system.

Provides a get_logger() factory that returns loggers pre-configured with
console and rotating file handlers. This is the single logging entry
point — never use print() in production code.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.utils.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "alphacore.log"


def get_logger(name: str) -> logging.Logger:
    """Return a fully configured logger with console + file handlers.

    Args:
        name: Dot-separated logger name, typically ``__name__``.

    Returns:
        A :class:`logging.Logger` instance ready for use.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(settings.LOG_LEVEL.upper())

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(settings.LOG_LEVEL.upper())
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        str(_LOG_FILE),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setLevel(settings.LOG_LEVEL.upper())
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

"""Centralised logging configuration for InsightAI.

A single rotating file handler plus a console handler are configured once and
reused across every module via :func:`get_logger`.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Log directory lives next to the project root regardless of CWD.
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "insightai.log"

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Track configured loggers so handlers are not attached twice (Streamlit reruns
# the script on every interaction, which would otherwise duplicate handlers).
_configured: set[str] = set()


def get_logger(name: str = "insightai", level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
        level: Minimum logging level.

    Returns:
        A :class:`logging.Logger` with rotating-file and console handlers.
    """
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _configured.add(name)
    return logger

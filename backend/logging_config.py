"""Shared local logging setup for the backend."""

import logging
import os
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _resolve_path(value, default):
    selected = os.getenv(value, default)
    if os.path.isabs(selected):
        return selected
    return os.path.join(BASE_DIR, selected)


def log_file_path():
    return os.path.join(_resolve_path("LOG_DIR", "logs"), "jobagent.log")


def configure_logging():
    """Configure one rotating file handler plus a concise console handler."""
    logger = logging.getLogger("jobagent")
    if getattr(logger, "_jobagent_configured", False):
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    path = log_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_handler = RotatingFileHandler(
        path,
        maxBytes=_env_int("LOG_MAX_BYTES", 2 * 1024 * 1024),
        backupCount=_env_int("LOG_BACKUP_COUNT", 5),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    logger._jobagent_configured = True
    logger.info("Logging initialized at %s", path)
    return logger

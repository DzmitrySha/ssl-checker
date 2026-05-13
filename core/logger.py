"""Настройка loguru: консоль (INFO) и файлы в LOGS_DIR (DEBUG, ротация по полуночи)."""

from __future__ import annotations

import sys

from loguru import logger

from config.settings import LOGS_DIR

logger.remove()
log_fmt = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
logger.add(sys.stdout, format=log_fmt, level="INFO", colorize=True)

file_fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger.add(
    LOGS_DIR / "app_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    format=file_fmt,
    level="DEBUG",
    compression="zip",
)

__all__ = ["logger"]

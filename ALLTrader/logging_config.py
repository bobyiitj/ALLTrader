"""Structured logging via loguru with a console sink and optional JSON sink."""
from __future__ import annotations

import sys

from loguru import logger

from config import settings


def configure_logging(json_sink: bool = False) -> None:
    """Configure loguru sinks. Idempotent.

    Args:
        json_sink: If True, also write JSON-formatted logs to logs/app.jsonl.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        backtrace=False,
        diagnose=False,
    )
    if json_sink:
        log_dir = settings.state_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "app.jsonl",
            level=settings.log_level,
            serialize=True,
            rotation="10 MB",
            retention=5,
        )


__all__ = ["configure_logging", "logger"]

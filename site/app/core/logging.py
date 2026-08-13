"""Централизованная конфигурация логирования сайта.

Единый формат для всех app-логгеров, уровень — из `LOG_LEVEL` (env, default INFO).
Логи идут в stdout (12-factor: контейнер собирает через `docker logs`).
Шумные сторонние логгеры приглушены.
"""
from __future__ import annotations

import logging
from logging.config import dictConfig

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = settings.log_level.upper()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"handlers": ["console"], "level": level},
        }
    )
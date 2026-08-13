"""Централизованная конфигурация логирования воркера.

Единый формат, уровень — из `LOG_LEVEL` (env, default INFO), логи в stdout.
Шумные логгеры `httpx`/`openai` приглушены до WARNING — это убирает спам
`GET /api/reviews?status=new "200 OK"` каждые WORKER_POLL_INTERVAL секунд
и httpx-логи openai SDK; ошибки WARNING+ остаются видны.
"""
from __future__ import annotations

import logging
from logging.config import dictConfig

from config import get_settings


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
    # Приглушить шум опроса и openai SDK; ошибки остаются видны.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
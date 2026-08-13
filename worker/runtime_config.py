"""Runtime-config — mtime-кеш config.json из shared volume.

Сайт пишет config.json через /admin; обработчик hot-reload'ит его по mtime —
смена провайдера/модели/промпта применяется на следующем цикле опроса без
рестарта. Секреты (ключи API) здесь НЕ хранятся — только runtime-параметры.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from config import get_settings


logger = logging.getLogger("worker.runtime_config")

DEFAULTS: dict[str, Any] = {
    "active_provider": "openai",
    "fallback_provider": "gigachat",
    "openai_enabled": True,
    "gigachat_enabled": True,
    "openai_model": "gpt-4.1-mini",
    "openai_base_url": "https://api.openai.com/v1",
    "openai_temperature": 0.3,
    "openai_max_tokens": 1024,
    "gigachat_model": "GigaChat-Max",
    "gigachat_temperature": 0.1,
    "gigachat_max_tokens": 500,
}


def _migrate_legacy(data: dict[str, Any]) -> dict[str, Any]:
    """Бесшовная миграция старого config.json (поле `provider`) → `active_provider`.

    Live-демо может иметь старый config.json без active_provider/fallback_provider.
    Маппим legacy `provider` в `active_provider`, а fallback — в противоположный.
    """
    if "active_provider" not in data and "provider" in data:
        legacy = data["provider"]
        data["active_provider"] = legacy
        if "fallback_provider" not in data:
            data["fallback_provider"] = "gigachat" if legacy == "openai" else "openai"
    return data


class RuntimeConfig:
    def __init__(self, file_path: str) -> None:
        self.path = Path(file_path)
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = dict(DEFAULTS)
        self._mtime: float | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._cache = dict(DEFAULTS)
            self._mtime = None
            return
        try:
            stat = self.path.stat()
        except OSError:
            return
        if self._mtime == stat.st_mtime:
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("runtime config read failed (%s): %s; keeping previous", self.path, exc)
            return
        merged = dict(DEFAULTS)
        merged.update(_migrate_legacy(data))
        self._cache = merged
        self._mtime = stat.st_mtime
        active = merged["active_provider"]
        active_model = merged["gigachat_model"] if active == "gigachat" else merged["openai_model"]
        logger.info(
            "Runtime config reloaded: active=%s fallback=%s model=%s",
            active, merged["fallback_provider"], active_model,
        )

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._load()
            return self._cache.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            self._load()
            return dict(self._cache)


_runtime: RuntimeConfig | None = None


def get_runtime_config() -> RuntimeConfig:
    global _runtime
    if _runtime is None:
        _runtime = RuntimeConfig(get_settings().runtime_config_path)
    return _runtime
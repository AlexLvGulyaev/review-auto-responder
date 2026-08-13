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
    "provider": "openai",
    "openai_model": "gpt-4.1-mini",
    "openai_base_url": "https://api.openai.com/v1",
    "yandex_folder_id": "",
}


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
        merged.update(data)
        self._cache = merged
        self._mtime = stat.st_mtime
        logger.info("Runtime config reloaded: provider=%s model=%s", merged["provider"], merged["openai_model"])

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
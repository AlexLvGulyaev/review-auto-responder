"""Загрузчик системного промпта.

Единый SOT текста промпта — файл на shared volume (`runtime_prompt_path`,
по умолчанию `/data/runtime/system_prompt.md`). Оператор редактирует его через
`/admin`; воркер hot-reload'ит по mtime — смена применяется на следующем цикле
без рестарта.

При отсутствии shared-файла (первый запуск / чистый volume) воркер
bootstrapp'ит его из вшитого `prompts/v1/system.md` (см. `worker.bootstrap_prompt`).
Если и вшитого файла нет — используется встроенный default.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from config import get_settings


logger = logging.getLogger("worker.prompt_loader")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts" / "v1"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system.md"


_BUILTIN_DEFAULT = (
    "Ты помощник поддержки, который отвечает на отзывы и комментарии клиентов на русском языке. "
    "Отвечай на каждый входящий текст: позитивный, негативный, нейтральный, короткий или эмоциональный. "
    "Сформируй естественный, вежливый и уместный ответ от лица компании. "
    "Если текст негативный — извинись и предложи помочь. "
    "Если позитивный — поблагодари. "
    "Если нейтральный — коротко отреагируй по существу без просьбы обязательно что-то уточнять. "
    "Не используй markdown, канцелярит, шаблонные фразы и подписи. "
    "Не повторяй отзыв дословно. "
    "Ответ на русском, не длиннее 3 предложений."
)


class _PromptCache:
    """mtime-кеш файла промпта на shared volume (hot-reload без рестарта)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._text: str = _BUILTIN_DEFAULT
        self._mtime: float | None = None

    def get(self) -> str:
        path = Path(get_settings().runtime_prompt_path)
        with self._lock:
            if not path.exists():
                return _BUILTIN_DEFAULT
            try:
                stat = path.stat()
            except OSError:
                return self._text
            if self._mtime == stat.st_mtime:
                return self._text
            try:
                self._text = path.read_text(encoding="utf-8").strip() or _BUILTIN_DEFAULT
                self._mtime = stat.st_mtime
                logger.info("System prompt reloaded from %s (%s bytes)", path, len(self._text))
            except OSError as exc:
                logger.warning("System prompt read failed (%s): %s; keeping previous", path, exc)
            return self._text


_cache = _PromptCache()


def load_system_prompt() -> str:
    """Текущий системный промпт (mtime-кеш shared-файла)."""
    return _cache.get()
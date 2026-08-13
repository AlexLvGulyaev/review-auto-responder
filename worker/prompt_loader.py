"""Загрузчик системного промпта.

Единый SOT текста промпта — `prompts/v1/system.md` (не хардкод в коде).
Override: если в runtime-config задан `system_prompt_override` (через /admin),
используется он — применяется на следующем цикле без рестарта (паттерн PEcb08 F4).
"""

from __future__ import annotations

import logging
from pathlib import Path

from runtime_config import get_runtime_config


logger = logging.getLogger("worker.prompt_loader")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts" / "v1"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system.md"


def load_system_prompt() -> str:
    override = (get_runtime_config().get("system_prompt_override") or "").strip()
    if override:
        return override

    if not SYSTEM_PROMPT_FILE.exists():
        logger.warning("System prompt file not found: %s; using built-in default", SYSTEM_PROMPT_FILE)
        return _BUILTIN_DEFAULT
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()


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
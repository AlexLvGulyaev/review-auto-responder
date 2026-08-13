import logging
import time

from models import ReviewTone
from prompt_loader import load_system_prompt
from providers import (
    ProviderNotConfigured,
    build_active_provider,
    build_fallback_provider,
)


logger = logging.getLogger("worker.processor")

POSITIVE_MARKERS = {
    "спасибо", "отлично", "супер", "класс", "хорош", "понрав", "рекоменд",
    "быстро", "удобно", "прекрас", "идеально", "love", "great", "awesome",
}
NEGATIVE_MARKERS = {
    "плохо", "ужас", "отврат", "проблем", "не работает", "ошибка", "долго",
    "медленно", "разочар", "сломал", "недоволен", "bad", "terrible", "awful",
}


def detect_tone(review_text: str) -> ReviewTone:
    text = review_text.lower()
    positive_score = sum(1 for marker in POSITIVE_MARKERS if marker in text)
    negative_score = sum(1 for marker in NEGATIVE_MARKERS if marker in text)

    if negative_score > positive_score:
        return ReviewTone.NEGATIVE
    if positive_score > negative_score:
        return ReviewTone.POSITIVE
    return ReviewTone.NEUTRAL


def build_fallback_response(review_text: str) -> str:
    tone = detect_tone(review_text)

    if tone == ReviewTone.NEGATIVE:
        return (
            "Нам жаль, что у вас остались негативные впечатления. "
            "Спасибо, что сообщили об этом. Пожалуйста, свяжитесь с нашей поддержкой, "
            "и мы постараемся помочь как можно быстрее."
        )

    if tone == ReviewTone.POSITIVE:
        return (
            "Спасибо за ваш отзыв и добрые слова. Нам очень приятно, "
            "что у вас остались положительные впечатления."
        )

    return (
        "Спасибо за ваш отзыв. Мы внимательно его изучили и учтем ваши замечания. "
        "Если захотите, можете поделиться деталями, чтобы мы смогли отреагировать точнее."
    )


async def _try_provider(provider, system_prompt: str, review_text: str) -> tuple[str, dict | None]:
    """Один провайдер. Возвращает (text, meta) при успехе или (None, reason)."""
    started = time.perf_counter()
    try:
        text = await provider.generate(system_prompt, review_text)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if text:
            return text, {
                "provider": provider.name,
                "model": provider.model_name,
                "latency_ms": latency_ms,
                "tokens": getattr(provider, "last_usage", None),
                "fallback_reason": None,
            }
        logger.warning("Provider %s returned empty response", provider.name)
        return None, "empty_response"
    except ProviderNotConfigured as exc:
        logger.info("Provider not configured (%s)", exc)
        return None, "provider_not_configured"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Provider %s request failed: %s", provider.name, exc)
        return None, "provider_error"


async def generate_response(review_text: str) -> tuple[str, dict]:
    """Сгенерировать ответ через активный провайдер (runtime-config).

    Возвращает кортеж `(text, meta)`, где `meta` несёт observability-данные для
    execution-трассировки: `provider`, `model`, `latency_ms`, `fallback_reason`
    (если применён fallback), `tokens` (если провайдер вернул usage, иначе None).

    Цепочка fallback: активный LLM → fallback LLM (если включён и сконфигурирован)
    → словарные шаблоны. Система продолжает отвечать даже без ключей —
    dict-fallback не падает.
    """
    system_prompt = load_system_prompt()

    # 1. Активный провайдер.
    try:
        active = build_active_provider()
        text, result = await _try_provider(active, system_prompt, review_text)
        if text is not None:
            return text, result
        active_reason = result
    except ProviderNotConfigured as exc:
        logger.info("Active provider not configured (%s), trying fallback", exc)
        active_reason = "provider_not_configured"

    # 2. Fallback LLM-провайдер.
    fallback = build_fallback_provider()
    if fallback is not None:
        text, result = await _try_provider(fallback, system_prompt, review_text)
        if text is not None:
            # Успех через fallback LLM — помечаем причину ухода с активного.
            result = {**result, "fallback_reason": f"llm_fallback_used:{active_reason}"}
            return text, result

    # 3. Словарные шаблоны.
    text = build_fallback_response(review_text)
    meta = {
        "provider": "fallback",
        "model": "fallback",
        "latency_ms": None,
        "tokens": None,
        "fallback_reason": active_reason,
    }
    return text, meta
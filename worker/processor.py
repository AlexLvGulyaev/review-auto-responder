import logging
import time

from models import ReviewTone
from prompt_loader import load_system_prompt
from providers import ProviderNotConfigured, build_provider


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


async def generate_response(review_text: str) -> tuple[str, dict]:
    """Сгенерировать ответ через активный провайдер (runtime-config).

    Возвращает кортеж `(text, meta)`, где `meta` несёт observability-данные для
    execution-трассировки: `provider`, `model`, `latency_ms`, `fallback_reason`
    (если применён fallback), `tokens` (если провайдер вернул usage, иначе None).

    Fallback на словарные шаблоны при: провайдер не настроен
    (ProviderNotConfigured), сбой API, пустой ответ. Система продолжает
    отвечать даже без ключа — fallback не падает.
    """
    try:
        provider = build_provider()
        system_prompt = load_system_prompt()
        started = time.perf_counter()
        text = await provider.generate(system_prompt, review_text)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if text:
            meta = {
                "provider": provider.name,
                "model": provider.model_name,
                "latency_ms": latency_ms,
                "tokens": getattr(provider, "last_usage", None),
                "fallback_reason": None,
            }
            return text, meta
        logger.warning("Provider %s returned empty response, using fallback", provider.name)
        fallback_reason = "empty_response"
    except ProviderNotConfigured as exc:
        logger.info("Provider not configured (%s), using fallback response generation", exc)
        fallback_reason = "provider_not_configured"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Provider request failed, using fallback: %s", exc)
        fallback_reason = "provider_error"

    text = build_fallback_response(review_text)
    meta = {
        "provider": "fallback",
        "model": "fallback",
        "latency_ms": None,
        "tokens": None,
        "fallback_reason": fallback_reason,
    }
    return text, meta
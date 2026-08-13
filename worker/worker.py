import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from client import ReviewSiteClient
from config import get_settings
from logging_config import configure_logging
from models import ReviewCreatePayload, ReviewStatus, ReviewTone, ReviewUpdatePayload
from processor import detect_tone, generate_response
from prompt_loader import SYSTEM_PROMPT_FILE
from runtime_config import get_runtime_config
from state import get_worker_state
from telegram_bot import send_new_review_notification


configure_logging()
logger = logging.getLogger("worker")
settings = get_settings()
state = get_worker_state()
client = ReviewSiteClient()


def is_ai_authored(review_name: str | None) -> bool:
    if not review_name:
        return False
    return review_name.strip().casefold() == settings.ai_author_name.strip().casefold()


def write_heartbeat() -> None:
    """Heartbeat для Docker healthcheck — метка каждой итерации цикла."""
    path = Path(settings.heartbeat_file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_iteration_at": datetime.now(timezone.utc).isoformat(),
        "target_site_url": settings.target_site_url,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def bootstrap_prompt() -> None:
    """Скопировать вшитый prompts/v1/system.md в shared volume при первом запуске.

    Shared-файл промпта — единственный SOT, редактируемый через /admin. Чтобы
    сайт всегда видел текущий промпт, а воркер — читал файл, а не default,
    при отсутствии shared-файла выкладываем начальный default из образа.
    Уже существующий файл НЕ перезаписываем (оператор мог его изменить).
    """
    target = Path(settings.runtime_prompt_path)
    if target.exists():
        return
    if not SYSTEM_PROMPT_FILE.exists():
        logger.warning("Bundled system prompt not found: %s; shared file left absent", SYSTEM_PROMPT_FILE)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SYSTEM_PROMPT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    logger.info("Bootstrapped system prompt from %s -> %s", SYSTEM_PROMPT_FILE, target)


def write_worker_status() -> None:
    """Status-снапшот в shared volume для /admin (liveness + статус провайдеров).

    Сайт читает этот файл без HTTP-вызова воркера. Секреты (ключи) НЕ пишем —
    только булевы флаги «сконфигурирован ли провайдер».
    """
    path = Path(settings.worker_status_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "worker_alive": True,
        "last_iteration_at": datetime.now(timezone.utc).isoformat(),
        "target_site_url": settings.target_site_url,
        "current_provider": get_runtime_config().get("provider"),
        "poll_interval": settings.worker_poll_interval,
        "providers": {
            "openai": bool(settings.openai_api_key),
            "gigachat": bool(settings.gigachat_auth_key),
            "yandex": bool(settings.yandex_api_key),
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def wait_for_site() -> None:
    logger.info("Waiting for target site at %s", settings.target_site_url)
    while True:
        try:
            await client.check_site()
            logger.info("Target site is ready")
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Target site is not ready yet: %s", exc)
            await asyncio.sleep(3)


def _step(stage_name: str, order: int, started: float) -> dict:
    """Собрать запись шага execution-сессии с таймингом (duration_ms)."""
    finished = time.perf_counter()
    return {
        "stage_name": stage_name,
        "step_order": order,
        "status": "ok",
        "duration_ms": int((finished - started) * 1000),
    }


async def process_review(review) -> None:
    """Обработка одного отзыва, обёрнутая в execution-сессию (start → шаги → finish).

    Каждый отзыв → 2 HTTP-вызова трассировки (start + finish-with-steps). Шаги:
    detect_tone, telegram, llm_call (несёт LLM-meta в step_metadata),
    persist_reply, mark_processed. На исключение — finish(status=error).
    """
    execution_id = await client.start_execution(
        review_id=review.id,
        route="review_processing",
    )
    session_started = time.perf_counter()
    steps: list[dict] = []
    provider_key: str | None = None
    model_name: str | None = None

    try:
        # Шаг 0: AI-authored guard — помечаем без ответа.
        if is_ai_authored(review.name):
            logger.info("Review id=%s was created by AI, marking as processed without reply", review.id)
            s = time.perf_counter()
            await client.update_review(
                review.id,
                ReviewUpdatePayload(status=ReviewStatus.PROCESSED, tone=ReviewTone.NEUTRAL),
            )
            steps.append({**_step("mark_processed", 0, s), "step_metadata": {"reason": "ai_authored"}})
            state.mark_processed(review.id)
            await client.finish_execution(
                execution_id,
                status="ok",
                duration_ms=int((time.perf_counter() - session_started) * 1000),
                steps=steps,
            )
            return

        # Шаг 1: detect_tone.
        s = time.perf_counter()
        tone = detect_tone(review.text)
        review.tone = tone.value
        steps.append({**_step("detect_tone", 1, s), "step_metadata": {"tone": tone.value}})

        # Шаг 2: telegram-уведомление (skipped, если уже нотифицирован).
        s = time.perf_counter()
        if not state.is_notified(review.id):
            notification_sent = await send_new_review_notification(review)
            if notification_sent:
                state.mark_notified(review.id)
                steps.append({**_step("telegram", 2, s), "step_metadata": {"sent": True}})
            else:
                steps.append({**_step("telegram", 2, s), "status": "skipped", "step_metadata": {"sent": False}})
        else:
            steps.append({**_step("telegram", 2, s), "status": "skipped", "step_metadata": {"already_notified": True}})

        # Дедупликация по локальному состоянию.
        if state.is_processed(review.id):
            logger.info("Review id=%s already processed in local state, skipping duplicate", review.id)
            steps.append({"stage_name": "mark_processed", "step_order": 5, "status": "skipped",
                          "duration_ms": 0, "step_metadata": {"reason": "already_processed"}})
            await client.finish_execution(
                execution_id,
                status="ok",
                duration_ms=int((time.perf_counter() - session_started) * 1000),
                steps=steps,
            )
            return

        # Шаг 3: llm_call — генерация ответа (несёт provider/model/latency/tokens).
        s = time.perf_counter()
        response_text, llm_meta = await generate_response(review.text)
        steps.append({
            **_step("llm_call", 3, s),
            "step_metadata": llm_meta,
        })
        provider_key = llm_meta.get("provider")
        model_name = llm_meta.get("model")

        # Шаг 4: persist_reply — публикация ответа + перевод отзыва в processed.
        s = time.perf_counter()
        ai_reply = await client.create_review(
            ReviewCreatePayload(parent_id=review.id, name=settings.ai_author_name, text=response_text),
        )
        await client.update_review(review.id, ReviewUpdatePayload(status=ReviewStatus.PROCESSED, tone=tone))
        await client.update_review(ai_reply.id, ReviewUpdatePayload(status=ReviewStatus.PROCESSED, tone=ReviewTone.NEUTRAL))
        steps.append({**_step("persist_reply", 4, s), "step_metadata": {"reply_id": ai_reply.id}})

        # Шаг 5: mark_processed — фиксация локального состояния.
        s = time.perf_counter()
        state.mark_processed(ai_reply.id)
        state.mark_processed(review.id)
        steps.append({**_step("mark_processed", 5, s)})

        logger.info("Review id=%s processed", review.id)
        await client.finish_execution(
            execution_id,
            status="ok",
            duration_ms=int((time.perf_counter() - session_started) * 1000),
            provider_key=provider_key,
            model_name=model_name,
            metadata={"reply_id": ai_reply.id},
            steps=steps,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Review id=%s processing failed: %s", review.id, exc)
        try:
            await client.finish_execution(
                execution_id,
                status="error",
                duration_ms=int((time.perf_counter() - session_started) * 1000),
                provider_key=provider_key,
                model_name=model_name,
                metadata={"error": str(exc)[:500]},
                steps=steps,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to record execution error for review id=%s", review.id)


async def process_new_reviews() -> int:
    reviews = await client.fetch_new_reviews()

    for review in reviews:
        logger.info("Processing review id=%s", review.id)
        await process_review(review)

    return len(reviews)


async def main() -> None:
    await wait_for_site()
    bootstrap_prompt()
    logger.info(
        "Worker started with poll interval=%s seconds, target site=%s",
        settings.worker_poll_interval,
        settings.target_site_url,
    )

    while True:
        try:
            processed_count = await process_new_reviews()
            if processed_count:
                logger.info("Processed %s review(s) in current iteration", processed_count)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Iteration failed, continuing: %s", exc)
        write_heartbeat()
        write_worker_status()
        await asyncio.sleep(settings.worker_poll_interval)


if __name__ == "__main__":
    asyncio.run(main())
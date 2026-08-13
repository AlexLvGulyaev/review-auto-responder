"""Консоль состояния системы — read-only обзор здоровья для /admin.

Модель данных: `overall` + `components` (живые пробы с
latency) + метрики БД + текущий применённый конфиг + liveness воркера + статус
провайдеров + последние ошибки.

Сбор данных:
- БД: живой `SELECT 1` + метрики (отзывы/трейсы/аудит/последняя сессия) — на сессии сайта.
- Воркер: `status.json` из shared volume (воркер пишет liveness + bool-флаги
  «провайдер сконфигурирован» — БЕЗ секретов). Liveness = свежесть last_iteration_at.
- Промпт: мета файла- SOT (размер/mtime).

`build_system_status(db)` — переиспользуется в `admin_panel` (блок вверху конфига).
`GET /admin/status` — JSON-эндпоинт для будущего JS-дэшборда.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import admin_auth, prompt_info, read_runtime_config
from app.config import get_settings
from app.db.session import get_db_session
from app.models.audit import AuditLog
from app.models.execution import ExecutionSession
from app.models.review import Review, ReviewStatus


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/status", tags=["admin-status"])
settings = get_settings()

_LIVENESS_MULTIPLIER = 3  # worker_alive, если last_iteration_at не старше 3×poll_interval


def _read_worker_status() -> dict[str, Any]:
    """Прочитать status.json воркера из shared volume (воркер пишет, сайт читает)."""
    path = Path(settings.worker_status_path)
    if not path.exists():
        return {"available": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["available"] = True
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("worker status read failed (%s): %s", path, exc)
        return {"available": False}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _worker_liveness(status: dict[str, Any]) -> dict[str, Any]:
    """Вычислить worker_alive по свежести last_iteration_at (порог 3×poll_interval)."""
    if not status.get("available"):
        return {**status, "worker_alive": False, "age_seconds": None}
    last = _parse_iso(status.get("last_iteration_at"))
    poll = int(status.get("poll_interval") or 10)
    if last is None:
        return {**status, "worker_alive": False, "age_seconds": None}
    now = datetime.now(timezone.utc)
    age = (now - last).total_seconds()
    alive = age <= _LIVENESS_MULTIPLIER * poll
    return {**status, "worker_alive": alive, "age_seconds": round(age, 1)}


async def _db_probe(db: AsyncSession) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "error", "latency_ms": latency_ms, "detail": str(exc)[:200]}


async def _db_metrics(db: AsyncSession) -> dict[str, Any]:
    """Сводные метрики: отзывы, трейсы, аудит, последняя сессия обработки."""
    # Отзывы по статусу.
    total_reviews = await db.scalar(select(func.count()).select_from(Review)) or 0
    new_reviews = await db.scalar(
        select(func.count()).select_from(Review).where(Review.status == ReviewStatus.NEW)
    ) or 0
    processed_reviews = await db.scalar(
        select(func.count()).select_from(Review).where(Review.status == ReviewStatus.PROCESSED)
    ) or 0

    # Трейсы по статусу.
    total_exec = await db.scalar(select(func.count()).select_from(ExecutionSession)) or 0
    ok_exec = await db.scalar(
        select(func.count()).select_from(ExecutionSession).where(ExecutionSession.status == "ok")
    ) or 0
    error_exec = await db.scalar(
        select(func.count()).select_from(ExecutionSession).where(ExecutionSession.status == "error")
    ) or 0
    started_exec = await db.scalar(
        select(func.count()).select_from(ExecutionSession).where(ExecutionSession.status == "started")
    ) or 0

    # Аудит.
    audit_count = await db.scalar(select(func.count()).select_from(AuditLog)) or 0

    # Последняя сессия обработки.
    last_session_row = await db.execute(
        select(ExecutionSession).order_by(ExecutionSession.started_at.desc()).limit(1)
    )
    last = last_session_row.scalars().first()
    last_session = None
    if last is not None:
        last_session = {
            "id": last.id,
            "status": last.status,
            "provider_key": last.provider_key,
            "model_name": last.model_name,
            "duration_ms": last.duration_ms,
            "finished_at": last.finished_at.isoformat() if last.finished_at else None,
        }

    # Последние ошибки (контур execution-tracing).
    err_rows = await db.execute(
        select(ExecutionSession)
        .where(ExecutionSession.status == "error")
        .order_by(ExecutionSession.finished_at.desc())
        .limit(5)
    )
    recent_errors = []
    for s in err_rows.scalars().all():
        meta = s.execution_metadata or {}
        recent_errors.append({
            "id": s.id,
            "review_id": s.review_id,
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            "error": (meta.get("error") or "")[:200],
        })

    return {
        "reviews": {"new": new_reviews, "processed": processed_reviews, "total": total_reviews},
        "executions": {"ok": ok_exec, "error": error_exec, "started": started_exec, "total": total_exec},
        "audit_count": audit_count,
        "last_session": last_session,
        "recent_errors": recent_errors,
    }


async def build_system_status(db: AsyncSession) -> dict[str, Any]:
    """Сводка состояния системы для блока в /admin (ридонли)."""
    db_component = await _db_probe(db)
    db_component["name"] = "database"

    metrics = await _db_metrics(db) if db_component["status"] == "ok" else {
        "reviews": {"new": 0, "processed": 0, "total": 0},
        "executions": {"ok": 0, "error": 0, "started": 0, "total": 0},
        "audit_count": 0,
        "last_session": None,
        "recent_errors": [],
    }

    worker_raw = _read_worker_status()
    worker = _worker_liveness(worker_raw)

    config = read_runtime_config()
    current_config = {
        "active_provider": config.get("active_provider"),
        "fallback_provider": config.get("fallback_provider"),
        "openai_enabled": config.get("openai_enabled"),
        "gigachat_enabled": config.get("gigachat_enabled"),
        "openai_model": config.get("openai_model"),
        "openai_base_url": config.get("openai_base_url"),
        "openai_temperature": config.get("openai_temperature"),
        "openai_max_tokens": config.get("openai_max_tokens"),
        "gigachat_model": config.get("gigachat_model"),
        "gigachat_temperature": config.get("gigachat_temperature"),
        "gigachat_max_tokens": config.get("gigachat_max_tokens"),
        "prompt": prompt_info(),
    }

    # overall: degraded, если БД/воркер/down или есть зависшие started-сессии.
    components = {"api": {"status": "ok"}, "database": db_component}
    overall = "ok"
    if db_component["status"] != "ok":
        overall = "degraded"
    if worker.get("available") and not worker.get("worker_alive"):
        overall = "degraded"
    if not worker.get("available"):
        overall = "degraded"

    return {
        "overall": overall,
        "components": components,
        "db_metrics": metrics,
        "current_config": current_config,
        "worker": worker,
    }


@router.get("", response_class=JSONResponse)
async def admin_status_json(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    _identity=Depends(admin_auth),
) -> JSONResponse:
    """JSON-сводка состояния системы (read-only, demo допущен)."""
    return JSONResponse(await build_system_status(db))
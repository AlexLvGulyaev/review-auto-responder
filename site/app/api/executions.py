"""API execution-tracing — воркер пишет трассы обработки через эти эндпоинты.

Two-phase: `POST /api/executions` (start, status=started) → воркер обрабатывает,
собирает шаги в памяти → `PATCH /api/executions/{id}` (finish: status, steps,
duration). При падении воркера остаётся `started`-сессия (видна как зависшая).

Auth: `X-Worker-Token` (общий с `PATCH /api/reviews`). Отказ → 401 + audit.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.execution import ExecutionSession, ExecutionStep
from app.api.worker_auth import require_worker_token
from app.schemas import (
    ExecutionCreate,
    ExecutionFinish,
    ExecutionRead,
    ExecutionStepIn,
)

router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.post("", response_model=ExecutionRead, status_code=status.HTTP_201_CREATED)
async def start_execution(
    payload: ExecutionCreate,
    db: AsyncSession = Depends(get_db_session),
    _token: str = Depends(require_worker_token),
) -> ExecutionSession:
    session = ExecutionSession(
        review_id=payload.review_id,
        route=payload.route,
        status="started",
        provider_key=payload.provider_key,
        model_name=payload.model_name,
        execution_metadata=payload.metadata or {},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.patch("/{execution_id}", response_model=ExecutionRead)
async def finish_execution(
    payload: ExecutionFinish,
    execution_id: int = Path(ge=1),
    db: AsyncSession = Depends(get_db_session),
    _token: str = Depends(require_worker_token),
) -> ExecutionSession:
    session = await db.get(ExecutionSession, execution_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution session not found.")

    session.status = payload.status
    session.finished_at = datetime.now(timezone.utc)
    if payload.duration_ms is not None:
        session.duration_ms = payload.duration_ms
    if payload.provider_key is not None:
        session.provider_key = payload.provider_key
    if payload.model_name is not None:
        session.model_name = payload.model_name
    if payload.metadata:
        merged = dict(session.execution_metadata or {})
        merged.update(payload.metadata)
        session.execution_metadata = merged

    for step_in in payload.steps:
        step = ExecutionStep(
            execution_session_id=execution_id,
            stage_name=step_in.stage_name,
            step_order=step_in.step_order,
            status=step_in.status,
            started_at=step_in.started_at,
            finished_at=step_in.finished_at,
            duration_ms=step_in.duration_ms,
            step_metadata=step_in.step_metadata or {},
        )
        db.add(step)

    await db.commit()
    await db.refresh(session)
    return session
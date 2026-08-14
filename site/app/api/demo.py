"""Эндпоинты демо-сессий для публичного сайта отзывов.

- `POST /api/demo/start` — выпустить новый демо-токен (с IP-лимитом сессий/час).
- `GET /api/demo/status` — текущая квота по токену.

Транспорт — заголовок `X-Demo-Token` (клиент хранит токен в localStorage и шлёт
его на `POST /api/reviews` и `GET /api/demo/status`). Backend — единственный
SOT квоты.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db_session
from app.services.audit import client_ip
from app.services.demo_limiter import DemoLimiterService

settings = get_settings()
router = APIRouter(prefix="/api/demo", tags=["demo"])


class DemoStartPayload(BaseModel):
    """Опциональный client session_id при старте демо-сессии."""

    session_id: Optional[str] = Field(None, max_length=255)


class DemoStartResponse(BaseModel):
    """Демо-токен и информация о квоте."""

    token: str
    session_id: Optional[str] = None
    requests_limit: int
    requests_remaining: int
    rate_limit_per_minute: int
    expires_at: str


class DemoStatusResponse(BaseModel):
    """Текущее состояние демо-токена."""

    token: str
    session_id: Optional[str] = None
    requests_used: int
    requests_limit: int
    requests_remaining: int
    expires_at: Optional[str] = None
    is_active: bool


def _ensure_demo_enabled() -> None:
    """403 если demo-режим отключен на backend."""
    if not settings.demo_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo mode is not enabled on this instance",
        )


@router.post("/start", response_model=DemoStartResponse)
async def start_demo_session(
    request: Request,
    payload: DemoStartPayload = DemoStartPayload(),
    db: AsyncSession = Depends(get_db_session),
) -> DemoStartResponse:
    """Создать новый демо-токен для публичной формы.

    Токен передаётся как `X-Demo-Token` на каждый `POST /api/reviews`.
    """
    _ensure_demo_enabled()
    service = DemoLimiterService(db)
    demo = await service.create_session(
        client_ip=client_ip(request),
        session_id=payload.session_id,
    )
    await db.commit()
    return DemoStartResponse(
        token=demo.token,
        session_id=demo.session_id,
        requests_limit=demo.requests_limit,
        requests_remaining=max(0, demo.requests_limit - demo.requests_used),
        rate_limit_per_minute=settings.demo_rate_limit_per_minute,
        expires_at=demo.expires_at.isoformat(),
    )


@router.get("/status", response_model=DemoStatusResponse)
async def demo_status(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> DemoStatusResponse:
    """Текущая квота и срок демо-токена. Токен — из заголовка `X-Demo-Token`."""
    _ensure_demo_enabled()
    token = request.headers.get("x-demo-token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Demo-Token header is required",
        )
    service = DemoLimiterService(db)
    status_data = await service.get_status(token)
    return DemoStatusResponse(**status_data)
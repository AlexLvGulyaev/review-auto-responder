"""Лимиттер демо-сессий для публичной формы отзывов.

Три уровня ограничения (как в эталонной реализации demo-режима):
- max sessions per IP per hour — защита от массовой генерации сессий;
- min interval between requests (через rate_limit_per_minute) — защита от спама;
- max requests per session — защита от длительного абуза.

Backend — единственный SOT квоты: UI лишь отображает.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.demo_session import DemoSession

settings = get_settings()


class DemoLimiterService:
    """Управление демо-токенами, квотами и rate-limit'ами."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _active_sessions_for_ip(self, client_ip: str, hours: int = 1) -> int:
        """Сколько демо-сессий создано с этого IP за последние N часов."""
        if not client_ip:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(DemoSession).where(
                DemoSession.client_ip == client_ip,
                DemoSession.created_at >= cutoff,
                DemoSession.is_active.is_(True),
            )
        )
        return len(result.scalars().all())

    async def create_session(
        self,
        client_ip: str | None,
        session_id: str | None = None,
    ) -> DemoSession:
        """Создать новый демо-токен.

        HTTPException(429), если с IP уже создано слишком много сессий за час.
        """
        if settings.demo_max_sessions_per_ip_per_hour > 0 and client_ip:
            recent = await self._active_sessions_for_ip(client_ip, hours=1)
            if recent >= settings.demo_max_sessions_per_ip_per_hour:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many demo sessions from this IP address. Please try again later.",
                )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.demo_session_ttl_minutes)
        demo = DemoSession(
            token=self._generate_token(),
            session_id=session_id,
            client_ip=client_ip,
            requests_used=0,
            requests_limit=settings.demo_max_requests_per_session,
            is_active=True,
            created_at=now,
            expires_at=expires_at,
            last_request_at=None,
        )
        self.db.add(demo)
        await self.db.flush()
        await self.db.refresh(demo)
        return demo

    async def get_session(self, token: str) -> DemoSession | None:
        """Демо-сессия по токену или None."""
        result = await self.db.execute(select(DemoSession).where(DemoSession.token == token))
        return result.scalar_one_or_none()

    async def check_and_record_request(
        self,
        token: str,
        client_ip: str | None,
    ) -> DemoSession:
        """Валидировать токен и списать один запрос из квоты.

        HTTPException для отсутствующего/истёкшего/rate-limited/исчерпанного токена.
        """
        demo = await self.get_session(token)
        if demo is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid demo token",
            )

        now = datetime.now(timezone.utc)
        if not demo.is_active or demo.expires_at <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Demo session has expired. Please start a new demo session.",
            )

        # Rate limit: минимум `60 / rate_limit_per_minute` секунд между запросами.
        min_interval_seconds = 60.0 / max(settings.demo_rate_limit_per_minute, 1)
        if demo.last_request_at is not None:
            elapsed = (now - demo.last_request_at).total_seconds()
            if elapsed < min_interval_seconds:
                retry_after = int(min_interval_seconds - elapsed) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Demo rate limit exceeded. Please wait before sending the next message.",
                    headers={"Retry-After": str(retry_after)},
                )

        if demo.requests_used >= demo.requests_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demo request quota exhausted. Please start a new demo session.",
            )

        demo.requests_used += 1
        demo.last_request_at = now
        await self.db.flush()
        await self.db.refresh(demo)
        return demo

    async def get_status(self, token: str) -> dict:
        """Текущий статус квоты по токену."""
        demo = await self.get_session(token)
        if demo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demo session not found",
            )
        remaining = max(0, demo.requests_limit - demo.requests_used)
        return {
            "token": demo.token,
            "session_id": demo.session_id,
            "requests_used": demo.requests_used,
            "requests_limit": demo.requests_limit,
            "requests_remaining": remaining,
            "expires_at": demo.expires_at.isoformat() if demo.expires_at else None,
            "is_active": demo.is_active and demo.expires_at > datetime.now(timezone.utc),
        }

    async def cleanup_expired(self) -> int:
        """Деактивировать истёкшие демо-сессии."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(DemoSession).where(
                DemoSession.is_active.is_(True),
                DemoSession.expires_at < now,
            )
        )
        expired = result.scalars().all()
        for demo in expired:
            demo.is_active = False
        await self.db.flush()
        return len(expired)

    @staticmethod
    def _generate_token() -> str:
        """Opaque демо-токен."""
        return uuid.uuid4().hex
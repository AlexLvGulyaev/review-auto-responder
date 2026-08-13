"""Общий guard worker-токена с аудитом отказа.

Используется мутациями воркера: `PATCH /api/reviews/{id}` и `POST/PATCH /api/executions`.
При отсутствии/несовпадении `X-Worker-Token` → 401 + audit-запись `auth.worker_denied`.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db_session
from app.services.audit import AuditService, client_ip

settings = get_settings()


async def require_worker_token(
    request: Request,
    x_worker_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> str:
    """Проверить X-Worker-Token; на отказ — 401 + audit auth.worker_denied."""
    if x_worker_token and x_worker_token == settings.worker_api_token:
        return x_worker_token
    await AuditService(db).log_audit(
        action="auth.worker_denied",
        resource_type="worker_api",
        ip_address=client_ip(request),
        details={"path": request.url.path},
    )
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token.")
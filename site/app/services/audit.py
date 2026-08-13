"""Audit-сервис — персистентная запись admin/security-событий в `audit_logs`.

Контур отделён от execution-tracing. Секреты в `details` не пишутся.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def client_ip(request: Request) -> str | None:
    """Реальный IP клиента из прокси-заголовков или соединения."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip() or None
    if request.client:
        return request.client.host
    return None


class AuditService:
    """Async-запись audit-событий в БД."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_audit(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        user_role: str | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        audit = AuditLog(
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            details=details or {},
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(audit)
        logger.info(
            "audit: action=%s resource=%s/%s user=%s role=%s",
            action,
            resource_type,
            resource_id,
            user_id,
            user_role,
        )
        return audit
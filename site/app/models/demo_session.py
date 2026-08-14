"""Модель демо-сессии для публичного сайта отзывов.

Токенизированная сессия с квотой: ограничивает число публикаций отзывов
(каждая → LLM-генерация) на одного анонимного клиента. Порт модели DemoSession
из однотипной реализации demo-режима, в стиль SQLAlchemy 2.0 проекта.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DemoSession(Base):
    """Временная сессия с токеном, квотой запросов и окном жизни."""

    __tablename__ = "demo_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Опциональный клиентский session_id (для reviews не передаётся).
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    requests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    requests_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
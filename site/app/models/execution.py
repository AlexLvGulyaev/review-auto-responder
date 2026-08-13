"""Модели execution-tracing — observability обработки отзыва воркером.

Каждая обработка одного отзыва = `ExecutionSession` (status/провайдер/модель/
длительность), стадии пайплайна = `ExecutionStep` с таймингом и `step_metadata`
(для LLM-шага — провайдер/модель/латентность/tokens/fallback_reason).

Пишет воркер через API сайта (`POST /api/executions` start, `PATCH` finish);
сайт персистит в БД и рендерит `/admin/executions`. Бизнес-данные отзыва
живут в `reviews` — здесь только observability обработки.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ExecutionSession(Base):
    """Одна обработка одного отзыва воркером (один проход пайплайна)."""

    __tablename__ = "execution_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    review_id: Mapped[int | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="started")
    route: Mapped[str] = mapped_column(String(64), nullable=False, default="review_processing")
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    steps: Mapped[list["ExecutionStep"]] = relationship(
        "ExecutionStep",
        back_populates="execution_session",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExecutionStep.step_order",
    )


class ExecutionStep(Base):
    """Стадия внутри обработки отзыва (detect_tone/telegram/llm_call/...)."""

    __tablename__ = "execution_steps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    execution_session_id: Mapped[int] = mapped_column(
        ForeignKey("execution_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    execution_session: Mapped["ExecutionSession"] = relationship(
        "ExecutionSession",
        back_populates="steps",
    )
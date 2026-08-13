"""Admin-панель execution-трейсов — read-only просмотр сессий обработки.

`GET /admin/executions` — список с фильтрами (period/status/tone + поиск по
review_id); `GET /admin/executions/{id}` — детали со шагами. Бизнес-контент
отзыва (запрос пользователя, ответ системы, тональность) живёт в `reviews` —
роут eager-грузит его для карточек и правой панели. Auth: `admin_auth` (demo-токен
допущен — только просмотр, как остальные `/admin`-чтения). Просмотры не аудируются
(avoid self-noise).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import admin_auth
from app.db.session import get_db_session
from app.models.execution import ExecutionSession
from app.models.review import Review


BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(prefix="/admin/executions", tags=["admin-executions"])


# Период-фильтр → cutoff (UTC). None/"all" → без фильтра.
_PERIOD_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@router.get("", response_class=HTMLResponse)
async def list_executions(
    request: Request,
    review_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    period: str | None = Query(default=None),
    tone: str | None = Query(default=None),
    selected: int | None = Query(default=None),
    limit: int = Query(default=7, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    identity=Depends(admin_auth),
) -> HTMLResponse:
    # Поиск по id отзыва — str, чтобы пустое поле формы (review_id=") не давало 422.
    review_id_int = int(review_id.strip()) if review_id and review_id.strip().isdigit() else None
    stmt = select(ExecutionSession).options(selectinload(ExecutionSession.steps))
    if review_id_int is not None:
        stmt = stmt.where(ExecutionSession.review_id == review_id_int)
    if status_filter:
        stmt = stmt.where(ExecutionSession.status == status_filter)
    delta = _PERIOD_DELTAS.get(period) if period else None
    if delta is not None:
        stmt = stmt.where(ExecutionSession.started_at >= datetime.now(timezone.utc) - delta)
    if tone:
        # Тональность живёт на reviews — inner join (сессии без review при tone-фильтре
        # корректно отбрасываются: без отзыва нет тональности).
        stmt = stmt.join(Review, Review.id == ExecutionSession.review_id).where(Review.tone == tone)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(ExecutionSession.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    sessions = result.scalars().unique().all()

    # Eager-загрузка бизнеса: исходный отзыв (запрос + тональность) и дочерний
    # ответ системы (Review где parent_id = review_id). Для карточек нужна тональность
    # и текст отзыва; для правой панели — запрос и ответ. Pre-render 7 деталей.
    review_ids = [s.review_id for s in sessions if s.review_id is not None]
    reviews_map: dict[int, Review] = {}
    replies_map: dict[int, Review] = {}
    if review_ids:
        rres = await db.execute(select(Review).where(Review.id.in_(review_ids)))
        for r in rres.scalars():
            reviews_map[r.id] = r
        cres = await db.execute(select(Review).where(Review.parent_id.in_(review_ids)))
        for c in cres.scalars():
            replies_map[c.parent_id] = c

    # Master-detail: дефолтно первая запись (правая панель не пуста на входе).
    selected_id = selected if selected is not None else (sessions[0].id if sessions else None)

    return templates.TemplateResponse(
        "executions.html",
        {
            "request": request,
            "identity": identity,
            "is_demo": identity.is_demo,
            "sessions": sessions,
            "total": total,
            "limit": limit,
            "offset": offset,
            "selected_id": selected_id,
            "reviews_map": reviews_map,
            "replies_map": replies_map,
            "timedelta": timedelta,
            "filters": {
                "review_id": review_id,
                "status": status_filter,
                "period": period,
                "tone": tone,
            },
        },
    )


@router.get("/{execution_id}", response_class=HTMLResponse)
async def execution_detail(
    request: Request,
    execution_id: int,
    db: AsyncSession = Depends(get_db_session),
    identity=Depends(admin_auth),
) -> HTMLResponse:
    session = await db.get(ExecutionSession, execution_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution session not found.")
    # steps загружены lazy="selectin" — доступны без явного запроса.
    # Бизнес: исходный отзыв (запрос + тональность) и дочерний ответ системы.
    review = await db.get(Review, session.review_id) if session.review_id is not None else None
    reply = None
    if session.review_id is not None:
        rres = await db.execute(
            select(Review).where(Review.parent_id == session.review_id).limit(1)
        )
        reply = rres.scalars().first()
    return templates.TemplateResponse(
        "execution_detail.html",
        {
            "request": request,
            "identity": identity,
            "is_demo": identity.is_demo,
            "session": session,
            "review": review,
            "reply": reply,
            "timedelta": timedelta,
        },
    )
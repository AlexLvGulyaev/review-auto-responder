"""Admin-панель execution-трейсов — read-only просмотр сессий обработки.

`GET /admin/executions` — список с фильтрами; `GET /admin/executions/{id}` —
детали со шагами. Auth: `admin_auth` (demo-токен допущен — только просмотр,
как остальные `/admin`-чтения). Просмотры не аудируются (avoid self-noise).
"""
from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import admin_auth
from app.db.session import get_db_session
from app.models.execution import ExecutionSession


BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(prefix="/admin/executions", tags=["admin-executions"])


def _parse_date(value: str | None, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
        return datetime.combine(d, time.max) if end_of_day else d
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {value}")


@router.get("", response_class=HTMLResponse)
async def list_executions(
    request: Request,
    review_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    provider: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _identity=Depends(admin_auth),
) -> HTMLResponse:
    stmt = select(ExecutionSession)
    if review_id is not None:
        stmt = stmt.where(ExecutionSession.review_id == review_id)
    if status_filter:
        stmt = stmt.where(ExecutionSession.status == status_filter)
    if provider:
        stmt = stmt.where(ExecutionSession.provider_key == provider)
    started_from = _parse_date(date_from)
    started_to = _parse_date(date_to, end_of_day=True)
    if started_from:
        stmt = stmt.where(ExecutionSession.started_at >= started_from)
    if started_to:
        stmt = stmt.where(ExecutionSession.started_at <= started_to)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(ExecutionSession.started_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    sessions = result.scalars().unique().all()

    return templates.TemplateResponse(
        "executions.html",
        {
            "request": request,
            "sessions": sessions,
            "total": total,
            "limit": limit,
            "offset": offset,
            "filters": {
                "review_id": review_id,
                "status": status_filter,
                "provider": provider,
                "date_from": date_from,
                "date_to": date_to,
            },
        },
    )


@router.get("/{execution_id}", response_class=HTMLResponse)
async def execution_detail(
    request: Request,
    execution_id: int,
    db: AsyncSession = Depends(get_db_session),
    _identity=Depends(admin_auth),
) -> HTMLResponse:
    session = await db.get(ExecutionSession, execution_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution session not found.")
    # steps загружены lazy="selectin" — доступны без явного запроса.
    return templates.TemplateResponse(
        "execution_detail.html",
        {"request": request, "session": session},
    )
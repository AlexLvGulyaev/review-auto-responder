"""Admin-панель аудита — read-only просмотр audit_logs.

`GET /admin/audit` — список с фильтрами (action, resource_type, user_id,
date_from, date_to, limit/offset). `GET /admin/audit/{id}` — деталь.
Auth: `admin_auth` (demo-токен допущен — только просмотр). Read-only-просмотры
не аудируются, чтобы не создавать self-noise (как в эталонном AuditLog).
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
from app.models.audit import AuditLog


BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])


def _parse_date(value: str | None, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
        return datetime.combine(d, time.max) if end_of_day else d
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {value}")


@router.get("", response_class=HTMLResponse)
async def list_audit(
    request: Request,
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    user_id_param: str | None = Query(default=None, alias="user_id"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    identity=Depends(admin_auth),
) -> HTMLResponse:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if user_id_param:
        stmt = stmt.where(
            (AuditLog.user_id == user_id_param) | (AuditLog.user_name == user_id_param)
        )
    started_from = _parse_date(date_from)
    started_to = _parse_date(date_to, end_of_day=True)
    if started_from:
        stmt = stmt.where(AuditLog.created_at >= started_from)
    if started_to:
        stmt = stmt.where(AuditLog.created_at <= started_to)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    entries = result.scalars().unique().all()

    return templates.TemplateResponse(
        "audit.html",
        {
            "request": request,
            "identity": identity,
            "is_demo": identity.is_demo,
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
            "filters": {
                "action": action,
                "resource_type": resource_type,
                "user_id": user_id_param,
                "date_from": date_from,
                "date_to": date_to,
            },
        },
    )


@router.get("/{audit_id}", response_class=HTMLResponse)
async def audit_detail(
    request: Request,
    audit_id: int,
    db: AsyncSession = Depends(get_db_session),
    identity=Depends(admin_auth),
) -> HTMLResponse:
    entry = await db.get(AuditLog, audit_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit entry not found.")
    return templates.TemplateResponse(
        "audit_detail.html",
        {"request": request, "identity": identity, "is_demo": identity.is_demo, "entry": entry},
    )
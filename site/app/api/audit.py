"""Admin-панель аудита — read-only просмотр audit_logs.

`GET /admin/audit` — список с фильтрами (period, action, resource_type,
user_id, limit/offset) в стиле эталонного AuditLog (AI Curator).
`GET /admin/audit/{id}` — деталь. Auth: `admin_auth` (demo-токен допущен —
только просмотр). Read-only-просмотры не аудируются, чтобы не создавать
self-noise (как в эталонном AuditLog).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


# Период-фильтр → cutoff (UTC). None/"all" → без фильтра. Как в Логах.
_PERIOD_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

# Замкнутые словари значений для фильтров-селектов (SOT; совпадает с
# классификацией action_badge в шаблоне и с вызовами AuditService.log_audit).
AUDIT_ACTIONS = [
    "admin.login_success",
    "admin.login_failed",
    "admin.rbac_denied",
    "admin.config_update",
    "admin.provider_test",
    "auth.worker_denied",
]
AUDIT_RESOURCE_TYPES = [
    "admin_session",
    "runtime_config",
    "provider",
    "worker_api",
]


@router.get("", response_class=HTMLResponse)
async def list_audit(
    request: Request,
    period: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    user_id_param: str | None = Query(default=None, alias="user_id"),
    selected: int | None = Query(default=None),
    limit: int = Query(default=7, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    identity=Depends(admin_auth),
) -> HTMLResponse:
    # Нормализуем пустые поля формы → None (форма сабмитит action= и т.п.).
    action = action.strip() or None if action else None
    resource_type = resource_type.strip() or None if resource_type else None
    user_id_param = user_id_param.strip() or None if user_id_param else None
    period = period or None

    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if user_id_param:
        stmt = stmt.where(
            (AuditLog.user_id == user_id_param) | (AuditLog.user_name == user_id_param)
        )
    delta = _PERIOD_DELTAS.get(period) if period else None
    if delta:
        stmt = stmt.where(AuditLog.created_at >= datetime.now(timezone.utc) - delta)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    entries = result.scalars().unique().all()

    # Master-detail с pre-render: правая панель рендерит все 7 деталей страницы,
    # видимая — selected (или дефолтно первая). Полные данные — на самой строке
    # AuditLog, отдельный fetch не нужен (нет N+1).
    selected_id = selected
    if selected_id is None and entries:
        selected_id = entries[0].id

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
            "selected_id": selected_id,
            "actions": AUDIT_ACTIONS,
            "resource_types": AUDIT_RESOURCE_TYPES,
            "filters": {
                "period": period,
                "action": action,
                "resource_type": resource_type,
                "user_id": user_id_param,
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
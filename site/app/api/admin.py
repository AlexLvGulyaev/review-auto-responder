"""Операторская панель /admin — runtime-config обработчика.

Доступ — демо-RBAC на два токена:

- `ADMIN_TOKEN` (полный) и `ADMIN_DEMO_TOKEN` (read-only);
- `AdminIdentity` с ролью admin/demo;
- `admin_auth` — идентификация (чтение `/admin` допускает demo);
- `require_admin` — guard мутаций: POST `/admin` → 403 для demo;
- backend — единственная настоящая защита (прямой API-вызов с demo-токеном
  отклоняется на мутации, обход UI невозможен);
- UI-бейдж «Демо-режим: только просмотр» + disabled кнопка сохранения.

Транспорт: server-rendered Jinja2 + cookie-сессия. Секреты (ключи провайдеров)
в `config.json` НЕ хранятся — только runtime-параметры; `config.json` пишется
в shared volume, обработчик hot-reload'ит его по mtime.

Admin/security-события (логин, смена конфига, RBAC-отказ) пишутся в audit_logs
через `AuditService`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_db_session
from app.services.audit import AuditService, client_ip


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

COOKIE_NAME = "admin_token"

DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "active_provider": "openai",
    "fallback_provider": "gigachat",
    "openai_enabled": True,
    "gigachat_enabled": True,
    "openai_model": "gpt-4.1-mini",
    "openai_base_url": "https://api.openai.com/v1",
    "openai_temperature": 0.3,
    "openai_max_tokens": 1024,
    "gigachat_model": "GigaChat-Max",
    "gigachat_temperature": 0.1,
    "gigachat_max_tokens": 500,
}


class AdminIdentity(BaseModel):
    user_id: str
    user_name: str
    user_role: str = "admin"

    @property
    def is_demo(self) -> bool:
        return self.user_role == "demo"


def _identity_from_token(token: str | None) -> AdminIdentity | None:
    if not token:
        return None
    if settings.admin_token and token == settings.admin_token:
        return AdminIdentity(user_id="admin", user_name="admin", user_role="admin")
    if settings.admin_demo_token and token == settings.admin_demo_token:
        return AdminIdentity(user_id="demo", user_name="demo", user_role="demo")
    return None


def _identity_from_request(request: Request) -> AdminIdentity | None:
    if not settings.admin_auth_enabled:
        return AdminIdentity(user_id="admin", user_name="admin", user_role="admin")
    return _identity_from_token(request.cookies.get(COOKIE_NAME))


async def admin_auth(request: Request) -> AdminIdentity:
    """Идентификация для admin-endpoints (чтение). Demo допущен."""
    identity = _identity_from_request(request)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token required")
    return identity


async def require_admin(
    request: Request,
    admin: AdminIdentity = Depends(admin_auth),
    db: AsyncSession = Depends(get_db_session),
) -> AdminIdentity:
    """Guard мутаций: demo-роль → 403 + audit admin.rbac_denied. Backend — единственная защита."""
    if admin.is_demo:
        await AuditService(db).log_audit(
            action="admin.rbac_denied",
            resource_type="runtime_config",
            user_id=admin.user_id,
            user_name=admin.user_name,
            user_role=admin.user_role,
            ip_address=client_ip(request),
            details={"path": request.url.path},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo access is read-only")
    return admin


# --- config.json read/write (shared volume) ---------------------------------


def _config_path() -> Path:
    return Path(settings.runtime_config_path)


def _migrate_legacy_provider(data: dict[str, Any]) -> dict[str, Any]:
    """Бесшовная миграция старого config.json (поле `provider`) → `active_provider`.

    Live-демо может иметь config.json без active_provider/fallback_provider.
    Маппим legacy `provider` в `active_provider`, fallback — в противоположный.
    """
    if "active_provider" not in data and "provider" in data:
        legacy = data["provider"]
        data["active_provider"] = legacy
        if "fallback_provider" not in data:
            data["fallback_provider"] = "gigachat" if legacy == "openai" else "openai"
    return data


def read_runtime_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return dict(DEFAULT_RUNTIME_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("runtime config read failed (%s): %s; using defaults", path, exc)
        return dict(DEFAULT_RUNTIME_CONFIG)
    merged = dict(DEFAULT_RUNTIME_CONFIG)
    merged.update(_migrate_legacy_provider(data))
    return merged


def write_runtime_config(payload: dict[str, Any]) -> None:
    """Атомарная запись config.json в shared volume."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    # Атомарная замена: пишем во временный файл, затем os.replace.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- system_prompt.md read/write (shared volume, файл-SOT) ------------------


def _prompt_path() -> Path:
    return Path(settings.runtime_prompt_path)


def read_prompt_text() -> str:
    """Текущий текст системного промпта из shared-файла (SOT)."""
    path = _prompt_path()
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("prompt file read failed (%s): %s", path, exc)
        return ""


def write_prompt_text(text: str) -> None:
    """Атомарная запись system_prompt.md в shared volume (воркер hot-reload'ит по mtime)."""
    path = _prompt_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".prompt.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def prompt_info() -> dict[str, Any]:
    """Ридонли-мета о файле промпта для блока «Состояние системы»."""
    path = _prompt_path()
    if not path.exists():
        return {"source": "file", "exists": False, "size": 0, "mtime": None}
    try:
        stat = path.stat()
        return {
            "source": "file",
            "exists": True,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    except OSError:
        return {"source": "file", "exists": False, "size": 0, "mtime": None}


# --- routes -----------------------------------------------------------------


@router.get("")
async def admin_panel(request: Request, db: AsyncSession = Depends(get_db_session)):
    identity = _identity_from_request(request)
    if identity is None:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    # Локальный импорт — разрывает цикл admin ↔ admin_status.
    from app.api.admin_status import build_system_status

    config = read_runtime_config()
    # Flash-сообщение результата «Проверить» (?test=ok|err&prov=...&msg=...).
    test_result = None
    test_param = request.query_params.get("test")
    if test_param in ("ok", "err"):
        test_result = {
            "ok": test_param == "ok",
            "provider": request.query_params.get("prov", ""),
            "message": request.query_params.get("msg", ""),
        }
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "identity": identity,
            "is_demo": identity.is_demo,
            "config": config,
            "prompt_text": read_prompt_text(),
            "prompt_info": prompt_info(),
            "status": await build_system_status(db),
            "saved": request.query_params.get("saved") == "1",
            "test_result": test_result,
        },
    )


@router.get("/login")
async def admin_login_form(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": error},
    )


@router.post("/login")
async def admin_login(
    request: Request,
    token: str = Form(...),
    db: AsyncSession = Depends(get_db_session),
):
    identity = _identity_from_token(token)
    ip = client_ip(request)
    if identity is None:
        await AuditService(db).log_audit(
            action="admin.login_failed",
            resource_type="admin_session",
            ip_address=ip,
            details={"path": request.url.path},
        )
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "error": "Неверный токен."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    await AuditService(db).log_audit(
        action="admin.login_success",
        resource_type="admin_session",
        user_id=identity.user_id,
        user_name=identity.user_name,
        user_role=identity.user_role,
        ip_address=ip,
    )
    response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # demo; за reverse-proxy с TLS можно выставить secure
        max_age=60 * 60 * 8,  # 8 часов
    )
    logger.info("Admin login: user_id=%s role=%s", identity.user_id, identity.user_role)
    return response


@router.post("/logout")
async def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.post("")
async def admin_save(
    request: Request,
    admin: AdminIdentity = Depends(require_admin),
    active_provider: str = Form(...),
    fallback_provider: str = Form(...),
    openai_enabled: str = Form(""),
    gigachat_enabled: str = Form(""),
    openai_model: str = Form(...),
    openai_base_url: str = Form(...),
    openai_temperature: float = Form(0.3),
    openai_max_tokens: int = Form(1024),
    gigachat_model: str = Form(...),
    gigachat_temperature: float = Form(0.1),
    gigachat_max_tokens: int = Form(500),
    system_prompt: str = Form(""),
    db: AsyncSession = Depends(get_db_session),
):
    # checkbox приходит только если отмечен; приводим к bool.
    openai_enabled_bool = openai_enabled in ("on", "true", "1", "yes")
    gigachat_enabled_bool = gigachat_enabled in ("on", "true", "1", "yes")

    previous = read_runtime_config()
    payload = {
        "active_provider": active_provider,
        "fallback_provider": fallback_provider,
        "openai_enabled": openai_enabled_bool,
        "gigachat_enabled": gigachat_enabled_bool,
        "openai_model": openai_model,
        "openai_base_url": openai_base_url,
        "openai_temperature": openai_temperature,
        "openai_max_tokens": openai_max_tokens,
        "gigachat_model": gigachat_model.strip(),
        "gigachat_temperature": gigachat_temperature,
        "gigachat_max_tokens": gigachat_max_tokens,
    }
    write_runtime_config(payload)
    changed_keys = sorted(k for k in payload if previous.get(k) != payload[k])

    # Промпт — файл-SOT: перезаписываем shared-файл, воркер hot-reload'ит по mtime.
    previous_prompt = read_prompt_text()
    new_prompt = system_prompt.strip()
    prompt_changed = previous_prompt.strip() != new_prompt
    if prompt_changed:
        write_prompt_text(new_prompt)

    await AuditService(db).log_audit(
        action="admin.config_update",
        resource_type="runtime_config",
        resource_id="config.json",
        user_id=admin.user_id,
        user_name=admin.user_name,
        user_role=admin.user_role,
        ip_address=client_ip(request),
        details={
            "active_provider": payload["active_provider"],
            "fallback_provider": payload["fallback_provider"],
            "openai_enabled": payload["openai_enabled"],
            "gigachat_enabled": payload["gigachat_enabled"],
            "openai_model": payload["openai_model"],
            "openai_base_url": payload["openai_base_url"],
            "openai_temperature": payload["openai_temperature"],
            "openai_max_tokens": payload["openai_max_tokens"],
            "gigachat_model": payload["gigachat_model"],
            "gigachat_temperature": payload["gigachat_temperature"],
            "gigachat_max_tokens": payload["gigachat_max_tokens"],
            "prompt_len": len(new_prompt),
            "prompt_changed": prompt_changed,
            "changed_keys": changed_keys,
        },
    )
    active_model = payload["openai_model"] if payload["active_provider"] == "openai" else payload["gigachat_model"]
    logger.info(
        "Runtime config updated by user_id=%s role=%s: active=%s fallback=%s model=%s prompt_changed=%s",
        admin.user_id,
        admin.user_role,
        payload["active_provider"],
        payload["fallback_provider"],
        active_model,
        prompt_changed,
    )
    return RedirectResponse(url="/admin?saved=1", status_code=status.HTTP_303_SEE_OTHER)


# --- «Проверить» — real-тест провайдера через воркер ------------------------


_PROVIDER_TEST_TIMEOUT = 20.0  # секунды; LLM-вызов + 1-токенный тест


def _call_worker_provider_test(provider_key: str) -> dict[str, Any]:
    """Синхронный HTTP-вызов к внутреннему test-API воркера (stdlib urllib).

    Воркер держит LLM-ключи и SSL/CA-логику GigaChat; сайт их не получает.
    Запрос: POST {worker_test_url}/provider-test с header X-Worker-Token и
    JSON-телом {"provider": provider_key}. Возвращает распарсенный JSON-ответ
    воркера. Бросает исключение при сетевой/HTTP-ошибке — ловится вызывающим.
    """
    url = f"{settings.worker_test_url.rstrip('/')}/provider-test"
    body = json.dumps({"provider": provider_key}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Worker-Token": settings.worker_api_token,
        },
    )
    with urllib.request.urlopen(req, timeout=_PROVIDER_TEST_TIMEOUT) as resp:  # noqa: S310 — внутренний URL
        return json.loads(resp.read().decode("utf-8"))


def _flash_url(provider_key: str, result: dict[str, Any] | None, error: str | None) -> str:
    """Собрать URL flash-сообщения для /admin по результату теста."""
    from urllib.parse import urlencode

    if result is not None:
        ok = "ok" if result.get("ok") else "err"
        # message воркера уже несёт provider/статус/модель/latency; дополняем только
        # токенами (то, чего нет в message), без дубля latency.
        msg = result.get("message") or ("готов" if result.get("ok") else "не готов")
        tokens = result.get("tokens")
        if tokens is not None:
            msg = f"{msg} · {tokens} ток."
    else:
        ok = "err"
        msg = error or "воркер недоступен"
    return f"/admin?{urlencode({'test': ok, 'prov': provider_key, 'msg': msg})}"


@router.post("/test-provider")
async def admin_test_provider(
    request: Request,
    admin: AdminIdentity = Depends(require_admin),
    provider_key: str = Form(...),
    db: AsyncSession = Depends(get_db_session),
):
    """Прокси к внутреннему test-API воркера (кнопка «Проверить» в карточке).

    `require_admin` — demo → 403 + audit (как и на мутации конфига). Real-вызов
    выполняет воркер (держит ключи); сайт лишь проксирует. Результат → redirect
    на /admin?test=ok|err&prov=...&msg=... (flash в admin.html).
    """
    key = provider_key.strip().lower()
    if key not in ("openai", "gigachat"):
        return RedirectResponse(
            url=_flash_url(provider_key, None, "неизвестный провайдер"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    result: dict[str, Any] | None = None
    error: str | None = None
    try:
        result = await asyncio.to_thread(_call_worker_provider_test, key)
    except urllib.error.HTTPError as exc:
        error = f"воркер вернул HTTP {exc.code}"
        try:
            error = json.loads(exc.read().decode("utf-8")).get("message", error)
        except (ValueError, OSError):
            pass
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = f"воркер недоступен: {exc}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("provider-test proxy failed: %s", exc)
        error = f"внутренняя ошибка: {exc}"

    await AuditService(db).log_audit(
        action="admin.provider_test",
        resource_type="provider",
        resource_id=key,
        user_id=admin.user_id,
        user_name=admin.user_name,
        user_role=admin.user_role,
        ip_address=client_ip(request),
        details={"ok": bool(result and result.get("ok")), "result": result, "error": error},
    )
    return RedirectResponse(
        url=_flash_url(key, result, error),
        status_code=status.HTTP_303_SEE_OTHER,
    )
# 🔌 API_CONTRACT.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата:** 2026-08-13
**Статус:** Engineering Layer — контракты HTTP API сайта.

Базовый URL сайта: `http://localhost:8000` (после `docker compose up`).

---

## 🔌 1. Публичные эндпоинты отзывов

### 🔌 1.1. `GET /` — главная страница

HTML (Jinja2): форма отзыва + список отзывов с автообновлением. Не API.

### 🔌 1.2. `GET /health`

Health-эндпоинт для Deployment Verification/Validation.

**Ответ:** `200 OK`
```json
{ "status": "ok" }
```

### 🔌 1.3. `GET /api/reviews`

Список отзывов. Серверный фильтр по статусу.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `status` | `new` \| `processed` (query, опц.) | Если задан — только отзывы с этим статусом. Без параметра — все. |

**Ответ:** `200 OK`
```json
[
  {
    "id": 1,
    "parent_id": null,
    "name": "Иван",
    "text": "Отличный сервис!",
    "status": "new",
    "response": null,
    "tone": null,
    "created_at": "2026-08-13T10:00:00"
  }
]
```

> 📌 **Доработка:** в legacy фильтр `status=new` выполнялся на клиенте по полному списку. Теперь — серверный `?status=new`, воркер тянет только новые.

### 🔌 1.4. `POST /api/reviews`

Создание отзыва или комментария (ответа). **Без авторизации** (legacy-модель доступа; см. [🛡️ SECURITY_NOTES.md](SECURITY_NOTES.md)).

**Тело:**
```json
{
  "parent_id": null,
  "name": "Иван",
  "text": "Отличный сервис!"
}
```

- `parent_id` опционален. Если задан — проверяется существование родителя.
- Используется и клиентом (отзыв), и воркером (ответ как дочерний комментарий с `name = AI_AUTHOR_NAME`).

**Ответ:** `201 Created` — объект `ReviewRead` (как в списке).

### 🔌 1.5. `PATCH /api/reviews/{id}`

Обновление `status`/`response`/`tone`. **Авторизация:** заголовок `X-Worker-Token: <WORKER_API_TOKEN>`.

**Тело** (все поля опциональны):
```json
{ "status": "processed", "tone": "positive" }
```

**Ответ:** `200 OK` — объект `ReviewRead`.

**Без токена / неверный токен:** `401 Unauthorized` + запись `auth.worker_denied` в журнал аудита.

---

## 🖥️ 2. Операторская панель `/admin`

Доступ — демо-RBAC на два токена (admin/demo), role-based guard на backend (`admin_auth` — чтение, `require_admin` — мутация → 403 для demo).

### 🖥️ 2.1. Модель доступа

| Токен (cookie `admin_token`) | Роль | Чтение `/admin` | Мутация (POST `/admin`) |
|------------------------------|------|-----------------|-------------------------|
| `ADMIN_TOKEN` | admin | ✅ | ✅ |
| `ADMIN_DEMO_TOKEN` | demo | ✅ | ❌ `403` |
| (нет / невалидный) | — | → редирект на `/admin/login` | `401` |

> 📌 **Backend — единственный реальный guard.** Отключённые кнопки в UI demo-режима — удобство, не защита. Прямой POST `/admin` с demo-токеном отклоняется на backend (`require_admin` → `403`).

### 🖥️ 2.2. Эндпоинты

| Метод | Путь | Назначение | Auth |
|-------|------|-----------|------|
| `GET` | `/admin` | Конфиг-консоль: настройки провайдеров + промпт (файл-SOT) + блок «Состояние системы» (ридонли) | `admin_auth` (demo допущен) |
| `GET` | `/admin/login` | Форма ввода токена | — |
| `POST` | `/admin/login` | Логин: установка cookie `admin_token` (8 ч) | — |
| `POST` | `/admin/logout` | Удаление cookie | — |
| `POST` | `/admin` | Сохранение runtime-config в `config.json` + промпта в `system_prompt.md` | `require_admin` (demo → `403`) |
| `POST` | `/admin/test-provider` | Real-тест провайдера (проксирует во внутренний test-API воркера) | `require_admin` (demo → `403`) |
| `GET` | `/admin/status` | JSON-сводка состояния системы (overall/components/метрики/воркер/провайдеры) | `admin_auth` (demo допущен) |

### 🖥️ 2.3. Поля формы (POST `/admin`, form-data)

| Поле | Тип | Описание |
|------|-----|----------|
| `active_provider` | `openai` \| `gigachat` | Активный LLM-провайдер → `config.json` |
| `fallback_provider` | `openai` \| `gigachat` | Fallback LLM-провайдер (если ≠ активного) → `config.json` |
| `openai_enabled` | `on` (checkbox) | Включён ли OpenAI в цепочке fallback → `config.json` (bool) |
| `gigachat_enabled` | `on` (checkbox) | Включён ли GigaChat в цепочке fallback → `config.json` (bool) |
| `openai_model` | str | Модель OpenAI → `config.json` |
| `openai_base_url` | str | base_url для OpenAI / OpenAI-compatible endpoint → `config.json` |
| `openai_temperature` | float | Temperature OpenAI (по умолч. 0.3) → `config.json` |
| `openai_max_tokens` | int | Max tokens OpenAI (по умолч. 1024) → `config.json` |
| `gigachat_model` | str | Модель GigaChat → `config.json` |
| `gigachat_temperature` | float | Temperature GigaChat (по умолч. 0.1) → `config.json` |
| `gigachat_max_tokens` | int | Max tokens GigaChat (по умолч. 500) → `config.json` |
| `system_prompt` | str | Текст системного промпта → перезаписывает `system_prompt.md` (файл-SOT) |

Runtime-параметры → атомарная запись `config.json` (tempfile + `os.replace`) в shared
volume. Промпт (`system_prompt`) → атомарная запись `system_prompt.md` в тот же shared
volume. Воркер подхватывает оба по mtime на следующем цикле — без рестарта. Legacy-поле
`provider` (старый config.json) бесшовно мигрируется в `active_provider` при чтении.

> 📌 **Промпт — файл-SOT.** Единственный источник текста промпта — файл
> `system_prompt.md` на shared volume. Сохранение в `/admin` перезаписывает его.
> Поля `system_prompt_override` в config.json больше нет.

> ⚠️ Ключи API сюда **не** передаются и **не** хранятся — только в `.env`.
> `gigachat_base_url` хранится в `.env` воркера и отображается read-only.

### 🖥️ 2.3.1. `POST /admin/test-provider` — «Проверить» (form-data)

| Поле | Тип | Описание |
|------|-----|----------|
| `provider_key` | `openai` \| `gigachat` | Какого провайдера проверить |

Прокси к внутреннему test-API воркера (`POST http://review-worker:8001/provider-test`,
header `X-Worker-Token`). Воркер выполняет real-вызов (`build_provider_for_key` +
`test_connection`, 1-токенный вызов), возвращает `{ok, provider, model, latency_ms,
tokens, message}`. Сайт редиректит на `/admin?test=ok|err&prov=...&msg=...` (flash).
Demo → `403` + audit `admin.rbac_denied`. LLM-ключи остаются на воркере — сайт их
не получает.

### 🖥️ 2.4. `GET /admin/status` — состояние системы (JSON)

Read-only JSON-сводка (demo допущен). Формируется из живых проб БД + метрик +
`status.json` воркера из shared volume.

```json
{
  "overall": "ok",
  "components": {
    "api": { "status": "ok" },
    "database": { "name": "database", "status": "ok", "latency_ms": 1.02 }
  },
  "db_metrics": {
    "reviews": { "new": 0, "processed": 24, "total": 24 },
    "executions": { "ok": 10, "error": 0, "started": 0, "total": 10 },
    "audit_count": 12,
    "last_session": { "id": 10, "status": "ok", "provider_key": "gigachat", "model_name": "GigaChat-Max", "duration_ms": 1727, "finished_at": "..." },
    "recent_errors": []
  },
  "current_config": {
    "active_provider": "gigachat", "fallback_provider": "openai",
    "openai_enabled": true, "gigachat_enabled": true,
    "openai_model": "gpt-4.1-mini", "openai_base_url": "https://api.openai.com/v1",
    "openai_temperature": 0.3, "openai_max_tokens": 1024,
    "gigachat_model": "GigaChat-Max", "gigachat_temperature": 0.1, "gigachat_max_tokens": 500,
    "prompt": { "source": "file", "exists": true, "size": 1170, "mtime": "..." }
  },
  "worker": {
    "available": true, "worker_alive": true, "age_seconds": 3.1,
    "last_iteration_at": "...", "current_provider": "gigachat",
    "active_provider": "gigachat", "fallback_provider": "openai",
    "openai_enabled": true, "gigachat_enabled": true,
    "poll_interval": 5,
    "providers": { "openai": true, "gigachat": true },
    "gigachat_base_url": "https://gigachat.devices.sberbank.ru/api/v1",
    "telegram": true
  }
}
```

`overall = ok` если БД отвечает и воркер жив (и `status.json` доступен); иначе
`degraded`. `worker_alive` = `last_iteration_at` свежее `3 × poll_interval`.
`status.json` воркер пишет каждую итерацию в shared volume (liveness + bool-флаги
«провайдер сконфигурирован» + публичный `gigachat_base_url`, **без секретов**). Блок
«Состояние системы» в `/admin` рендерится из тех же данных server-side.

---

## 🔁 3. Execution tracing (`/api/executions`)

Воркер пишет трассы обработки отзывов через эти эндпоинты (у воркера нет
БД-сессии — он отдельный сервис). **Авторизация:** заголовок
`X-Worker-Token: <WORKER_API_TOKEN>` (общий с `PATCH /api/reviews`).

### 🔁 3.1. `POST /api/executions` — старт сессии

**Тело:**
```json
{ "review_id": 42, "route": "review_processing", "metadata": {} }
```

`review_id` опционален. Создаёт `execution_sessions` со `status=started`.

**Ответ:** `201 Created`
```json
{ "id": 7, "review_id": 42, "status": "started", "route": "review_processing", "started_at": "...", "execution_metadata": {}, "steps": [] }
```

### 🔁 3.2. `PATCH /api/executions/{id}` — финал сессии

Закрывает сессию: выставляет `status`, `finished_at`, `duration_ms`,
`provider_key`/`model_name`, мерджит `metadata`, персистит все шаги одной
транзакцией.

**Тело:**
```json
{
  "status": "ok",
  "duration_ms": 3200,
  "provider_key": "gigachat",
  "model_name": "GigaChat",
  "metadata": { "reply_id": 43 },
  "steps": [
    { "stage_name": "detect_tone", "step_order": 1, "status": "ok", "duration_ms": 0, "step_metadata": { "tone": "positive" } },
    { "stage_name": "llm_call", "step_order": 3, "status": "ok", "duration_ms": 3100, "step_metadata": { "provider": "gigachat", "model": "GigaChat", "latency_ms": 3100, "tokens": 180, "fallback_reason": null } }
  ]
}
```

| Поле | Тип | Описание |
|------|-----|----------|
| `status` | `ok` \| `error` | Результат обработки |
| `duration_ms` | int \| null | Длительность всей обработки |
| `provider_key` / `model_name` | str \| null | LLM-провайдер/модель (из LLM-meta) |
| `metadata` | dict | Доп. метаданные сессии |
| `steps` | list[`ExecutionStepIn`] | Шаги пайплайна (`stage_name`, `step_order`, `status` `ok`/`error`/`skipped`, `duration_ms`, `step_metadata`) |

**Ответ:** `200 OK` — объект `ExecutionRead` (сессия со `steps`).

**Без токена / неверный токен:** `401 Unauthorized` + `auth.worker_denied` в аудит.

> 📌 Двухфазная запись: 2 HTTP-вызова на отзыв. При падении воркера между start
> и finish остаётся `started`-сессия (диагностический признак зависшей обработки).

---

## 📜 4. Журнал аудита и трейсов (`/admin/audit`, `/admin/executions`)

Read-only панели observability. **Auth:** `admin_auth` (demo-токен допущен —
только просмотр, как остальные `/admin`-чтения). Просмотры **не** аудируются.

### 📜 4.1. `GET /admin/audit` — список записей аудита

| Параметр | Тип | Описание |
|----------|-----|----------|
| `action` | str (опц.) | Фильтр по действию (`admin.config_update`, ...) |
| `resource_type` | str (опц.) | Фильтр по типу ресурса |
| `user_id` | str (опц.) | Фильтр по `user_id` или `user_name` |
| `date_from` / `date_to` | `YYYY-MM-DD` (опц.) | Диапазон по `created_at` |
| `limit` / `offset` | int | Пагинация (default `100`/`0`, max `500`) |

Возвращает HTML-таблицу записей `audit_logs`.

### 📜 4.2. `GET /admin/audit/{id}` — деталь записи аудита

HTML-карточка: действие, ресурс, пользователь/роль, IP, время, `details` (JSON).

### 📜 4.3. `GET /admin/executions` — список трейсов обработки

| Параметр | Тип | Описание |
|----------|-----|----------|
| `review_id` | int (опц.) | Фильтр по отзыву |
| `status` | `ok`/`error`/`started` (опц.) | Фильтр по статусу |
| `provider` | str (опц.) | Фильтр по провайдеру |
| `date_from` / `date_to` | `YYYY-MM-DD` (опц.) | Диапазон по `started_at` |
| `limit` / `offset` | int | Пагинация (default `50`/`0`, max `200`) |

Возвращает HTML-таблицу сессий с шагами-чипами.

### 📜 4.4. `GET /admin/executions/{id}` — деталь сессии

HTML: параметры сессии (статус/провайдер/модель/длительность) + таблица шагов
пайплайна с `step_metadata` (для `llm_call` — provider/model/latency_ms/tokens/fallback_reason).

### 📜 4.5. События аудита

| Action | Триггер |
|--------|---------|
| `admin.login_success` / `admin.login_failed` | `POST /admin/login` |
| `admin.config_update` | `POST /admin` (успешное сохранение) |
| `admin.rbac_denied` | demo-попытка мутации → `403` |
| `auth.worker_denied` | плохой `X-Worker-Token` на `PATCH /api/reviews` / `/api/executions` → `401` |

> ⚠️ В `details` аудита не пишутся секреты и полный текст промпта
> (только `prompt_len` + `prompt_changed` + список изменённых ключей `changed_keys`).

---

## 📚 Связанные документы

- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура и путь данных.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность и демо-RBAC.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры провайдеров.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание.
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

**Без токена / неверный токен:** `403 Forbidden`.

---

## 🖥️ 2. Операторская панель `/admin`

Доступ по стандартному демо-сценарию APL: два токена (admin/demo), role-based guard на backend (`admin_auth` — чтение, `require_admin` — мутация → 403 для demo).

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
| `GET` | `/admin` | Форма runtime-config (или редирект на login) | `admin_auth` (demo допущен) |
| `GET` | `/admin/login` | Форма ввода токена | — |
| `POST` | `/admin/login` | Логин: установка cookie `admin_token` (8 ч) | — |
| `POST` | `/admin/logout` | Удаление cookie | — |
| `POST` | `/admin` | Сохранение runtime-config в `config.json` | `require_admin` (demo → `403`) |

### 🖥️ 2.3. Поля runtime-config (POST `/admin`, form-data)

| Поле | Тип | Описание |
|------|-----|----------|
| `provider` | `openai` \| `gigachat` \| `yandex` \| `custom` | Активный провайдер |
| `openai_model` | str | Имя модели (для yandex — URI с `<folder_id>`) |
| `openai_base_url` | str | base_url для openai/custom |
| `yandex_folder_id` | str | folder_id для YandexGPT |
| `system_prompt_override` | str | Override промпта (пусто = файл `prompts/v1/system.md`) |

Сохранение → атомарная запись `config.json` (tempfile + `os.replace`) в shared volume → воркер подхватывает по mtime на следующем цикле.

> ⚠️ Ключи API сюда **не** передаются и **не** хранятся — только в `.env`.

---

## 📚 Связанные документы

- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура и путь данных.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность и демо-RBAC.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры провайдеров.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание.
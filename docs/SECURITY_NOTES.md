# 🛡️ SECURITY_NOTES.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата:** 2026-08-13
**Статус:** Engineering Layer — безопасность, доступ, демо-RBAC.

---

## 🔐 1. Секреты

| Секрет | Где | Назначение |
|--------|-----|-----------|
| `WORKER_API_TOKEN` | `.env` (общий для site + worker) | Авторизация `PATCH` воркера |
| `ADMIN_TOKEN` | `.env` | Полный доступ к `/admin` (мутации) |
| `ADMIN_DEMO_TOKEN` | `.env` | Read-only доступ к `/admin` (демо) |
| `OPENAI_API_KEY` | `.env` | Провайдер OpenAI/«Свой» |
| `GIGACHAT_AUTH_KEY` | `.env` | Провайдер GigaChat (OAuth-обмен) |
| `YANDEX_API_KEY` | `.env` | Провайдер YandexGPT |
| `TELEGRAM_BOT_TOKEN` | `.env` | Уведомления оператору |

> ⚠️ **Все секреты — только в `.env`.** `.env` в `.gitignore`; в репозитории — `.env.example` с placeholder'ами `YOUR_*`. Ключи API **никогда** не попадают в `config.json` (shared volume) и не передаются через `/admin`.

---

## 🛡️ 2. Демо-RBAC для `/admin`

Реализован как демо-RBAC на два токена (admin/demo), role-based guard на backend.

### 🛡️ 2.1. Два токена, две роли

| Токен | `user_role` | `is_demo` | Возможности |
|-------|-------------|-----------|-------------|
| `ADMIN_TOKEN` | `admin` | `false` | Чтение + мутация runtime-config |
| `ADMIN_DEMO_TOKEN` | `demo` | `true` | Только чтение; мутация → `403` |

Токен передаётся через cookie `admin_token` (сессия 8 часов после `/admin/login`). Идентичность — `AdminIdentity(user_id, user_name, user_role)`; `is_demo` — производное свойство.

### 🛡️ 2.2. Две зависимости-гарда

| Зависимость | Допуск | Применение |
|-------------|--------|-----------|
| `admin_auth` | любой валидный токен (admin **и** demo) | `GET /admin` — чтение |
| `require_admin` | только `admin` (demo → `403`) | `POST /admin` — мутация |

> 📌 **Backend — единственный реальный guard.** В demo-режиме UI дополнительно отключает кнопку сохранения и показывает бейдж «👁 Демо-режим: только просмотр» — это удобство оператора, а не защита. Прямой `POST /admin` с demo-токеном (curl/инструмент) отклоняется на backend.

### 🛡️ 2.3. Почему не HTTP Basic

> ❌ **Failed Approach:** HTTP Basic с двумя пользователями. Минусы: браузер кеширует Basic-credentials и не позволяет «выйти» без закрытия вкладок; нет отдельного lifecycle у demo-доступа; сложнее отличить роли в логах. Токен-cookie + `AdminIdentity` решает это: явный login/logout, отдельный demo-токен со своим lifecycle, роль в audit-логах.

### 🛡️ 2.4. Отключение auth (только локальные тесты)

`ADMIN_AUTH_ENABLED=false` в `.env` переводит `_identity_from_request` в режим «все запросы — admin». **Только для локальной разработки/тестов**, не для публичного демо.

---

## 🔓 3. Доступ к публичному API отзывов

| Эндпоинт | Авторизация | Обоснование |
|----------|-------------|-------------|
| `GET /`, `GET /api/reviews`, `GET /health` | открыт | Публичный сайт + health |
| `POST /api/reviews` | открыт | Legacy-модель: клиент и воркер создают отзывы/комментарии без авторизации |
| `PATCH /api/reviews/{id}` | `X-Worker-Token` | Мутация статуса — только воркер |

> ⚠️ **Отложено (v1.0):** RBAC на `POST /api/reviews`. В публичной форме без авторизации это позволяет любому создавать отзывы/комментарии. Для demo/MVP допустимо; для prod — добавить токенизацию с квотой (см. §4 ниже). Это **намеренное ограничение границы v1.0**, задокументированное, а не упущение.

---

## 📊 4. Токенизация публичной формы (опциональное развитие)

Публичная форма отзыва запускает воркер → вызов LLM → стоимость. Для публичного
демо с расходом применима токенизация сессий с квотой на отзывы (лимиттер по
короткоживущим токенам/cookie) — ограничивает число генераций на клиента.

> 📌 **Статус:** отложено за границу v1.0. В текущей версии расход контролируется оператором (смена провайдера/fallback) и закрытостью демо-окружения. Вынесено в SPEC §8 как направление развития.

---

## 🔧 5. Токены по умолчанию

> ⚠️ Значения `change-me` в коде — заглушки. **Перед любым запуском кроме локального** задать реальные значения в `.env`: `WORKER_API_TOKEN`, `ADMIN_TOKEN`, `ADMIN_DEMO_TOKEN`. Развёртывание со значениями по умолчанию в публично доступном окружении — уязвимость.

---

## 📜 6. Audit trail (контур аудита)

Все admin/security-события пишутся в таблицу `audit_logs` (контур 3 observability):
кто (`user_id`/`user_name`/`user_role`), что (`action`), над чем
(`resource_type`/`resource_id`), откуда (`ip_address`), контекст (`details` JSON).

| Action | Триггер | Записывается |
|--------|---------|--------------|
| `admin.login_success` / `admin.login_failed` | `POST /admin/login` | user, ip, path |
| `admin.config_update` | `POST /admin` (сохранение) | provider/model/base_url, prompt_override_len, changed_keys |
| `admin.rbac_denied` | demo-попытка мутации → `403` | user, ip, path |
| `auth.worker_denied` | плохой `X-Worker-Token` → `401` | ip, path |

> 🛡️ **Что НЕ попадает в аудит:**
> - **Секреты** — ключи API, токены никогда не пишутся в `details`.
> - **Полный текст `system_prompt_override`** — только его длина и список изменённых ключей (`changed_keys`).
> - **Read-only-просмотры** (`/admin`, `/admin/audit`, `/admin/executions`) — не аудируются, чтобы журнал не засорялся self-noise.

Просмотр журнала: `GET /admin/audit` (read-only, demo-токен допущен). Деталь
записи: `GET /admin/audit/{id}`. См. [🔌 API_CONTRACT.md §4](API_CONTRACT.md).

IP-адрес извлекается по цепочке `X-Forwarded-For` → `X-Real-IP` → `client.host`
(корректно за обратным прокси с TLS-терминацией).

---

## 🔁 7. Execution tracing (контур observability обработки)

Трассы обработки каждого отзыва пишутся в `execution_sessions` + `execution_steps`
(контур 2 observability). Это **не безопасность**, а observability: статус
обработки, провайдер/модель, длительность, шаги пайплайна и LLM-метрики
(latency/tokens/fallback_reason). Сессия создаётся воркером через
`POST /api/executions` (start) и закрывается `PATCH /api/executions/{id}` (finish).

> 🛡️ **С точки зрения безопасности:** эндпоинты `/api/executions` защищены тем же
> `X-Worker-Token`, что и `PATCH /api/reviews` — внешняя запись трасс
> невозможна. При падении воркера между start и finish остаётся `started`-сессия
> (диагностический признак, не уязвимость). Просмотр `/admin/executions` —
> read-only за `admin_auth` (demo допущен).

См. [🏗️ ARCHITECTURE.md §7](ARCHITECTURE.md) и [🔌 API_CONTRACT.md §3](API_CONTRACT.md).

---

## 📚 Связанные документы

- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты HTTP API.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры провайдеров.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание и env.
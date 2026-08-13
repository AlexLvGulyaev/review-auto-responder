# 🏗️ ARCHITECTURE.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата:** 2026-08-13
**Статус:** Engineering Layer — архитектура и путь данных.

---

## 🎯 1. Назначение

Двухсервисная система автономного ответа на отзывы:

- **review-site** — FastAPI + PostgreSQL: публичный сайт отзывов, хранилище, операторская панель `/admin`.
- **review-worker** — асинхронный поллер: опрашивает сайт, определяет тон, генерирует ответ через LLM-провайдер, пишет ответ обратно, уведомляет оператора в Telegram.

Архитектура намеренно разделяет **хранение/UX** (сайт) и **автономную обработку** (воркер). Сайт — первичный Source of Truth статуса отзыва (`new`/`processed`); локальный `state.json` воркера — вторичный идемпотентный guard.

---

## 🧩 2. Компоненты

| Компонент | Технология | Ответственность |
|-----------|-----------|----------------|
| `review-site` | FastAPI, SQLAlchemy 2 (async), asyncpg, Jinja2 | Хранение отзывов, публичный UI, `/admin` runtime-config, `/health` |
| `review-worker` | asyncio, httpx, openai SDK, urllib (GigaChat) | Опрос, классификация тона, генерация ответа, write-back, Telegram |
| `db` | PostgreSQL 16 | Хранилище отзывов (самоссылающаяся модель `Review`) |
| `runtime-config` (volume) | shared volume `config.json` | Runtime-параметры (провайдер/модель/промпт); `/admin` пишет, воркер читает по mtime |

---

## 🗂️ 3. Модель данных

### 🗂️ 3.1. Таблица `reviews`

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | int PK | Идентификатор |
| `parent_id` | int FK → `reviews.id` | Самоссылка: дочерний комментарий (ответ) на родительский отзыв |
| `name` | str \| null | Имя автора (`AI_AUTHOR_NAME` для авто-ответов) |
| `text` | text | Текст отзыва/ответа |
| `status` | enum `new`/`processed` | **Первичный SOT** — обработан ли отзыв |
| `response` | str \| null | Зарезервировано (ответ публикуется дочерним комментарием) |
| `tone` | enum `positive`/`negative`/`neutral` \| null | Тональность (определяет воркер) |
| `created_at` | datetime | Время создания |

Threaded-структура: ответ воркера — это строка `reviews` с `parent_id = <id отзыва>`, `name = AI_AUTHOR_NAME`. Это сохраняет дерево комментариев сайта.

### 🗂️ 3.2. Локальный state воркера (`state.json`)

| Поле | Назначение |
|------|-----------|
| `notified_review_ids` | Отзывы, по которым уже отправлено Telegram-уведомление (предотвращает дубль, пока отзыв ещё `new`) |
| `processed_review_ids` | Defensive-проверка перед дорогой `generate_response` + `create_review` (окно до смены статуса на сайте) |

> 📌 **SOT-дисциплина:** статус на сайте — первичный. `state.json` покрывает только окно «воркер уже обработал, но сайт ещё не подтвердил `processed`» и идемпотентность при рестартах.

### 🗂️ 3.3. Таблица `execution_sessions` (контур 2 — execution tracing)

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | int PK | Идентификатор сессии обработки |
| `review_id` | int FK → `reviews.id` (SET NULL) | Обрабатываемый отзыв |
| `status` | `started`/`ok`/`error` | Статус обработки |
| `route` | str | Маршрут (`review_processing`) |
| `provider_key` | str \| null | LLM-провайдер (`gigachat`/`openai`/`fallback`/...) |
| `model_name` | str \| null | Имя модели |
| `duration_ms` | int \| null | Длительность всей обработки |
| `started_at` / `finished_at` | datetime | Время старта/финала |
| `execution_metadata` | JSONB | Метаданные сессии (напр. `reply_id`, `error`) |

### 🗂️ 3.4. Таблица `execution_steps` (стадии пайплайна)

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | int PK | Идентификатор шага |
| `execution_session_id` | int FK → `execution_sessions.id` (CASCADE) | Родительская сессия |
| `stage_name` | str | `detect_tone`/`telegram`/`llm_call`/`persist_reply`/`mark_processed` |
| `step_order` | int | Порядок шага |
| `status` | `ok`/`error`/`skipped` | Статус шага |
| `started_at` / `finished_at` | datetime \| null | Тайминг шага |
| `duration_ms` | int \| null | Длительность шага |
| `step_metadata` | JSONB | Для `llm_call`: `{provider, model, latency_ms, tokens, fallback_reason}` |

### 🗂️ 3.5. Таблица `audit_logs` (контур 3 — audit)

| Поле | Тип | Назначение |
|------|-----|-----------|
| `id` | int PK | Идентификатор записи |
| `user_id` / `user_name` / `user_role` | str \| null | Кто совершил действие |
| `action` | str | Тип события (`admin.config_update`, `auth.worker_denied`, ...) |
| `resource_type` / `resource_id` | str \| null | Над чем совершено |
| `ip_address` | str \| null | Откуда (`X-Forwarded-For` → `X-Real-IP` → `client.host`) |
| `details` | JSONB | Контекст (без секретов и полных промптов) |
| `created_at` | datetime | Время события |

> 📌 Таблицы observability создаются `Base.metadata.create_all` в lifespan сайта
> (Alembic не используется — idempotent для существующей БД демо).

---

## 🔀 4. Путь данных (data flow)

### 🔀 4.1. Схема

```mermaid
flowchart TD
    C([Клиент]) -->|POST /api/reviews| S[review-site]
    S -->|insert status=new| DB[(PostgreSQL)]
    W[review-worker] -->|GET /api/reviews?status=new| S
    S -->|только new| W
    W -->|POST /api/executions start| S
    S -->|execution_session status=started| DB
    W -->|detect_tone словарь| W
    W -->|Telegram notify опционально| T([Оператор])
    W -->|build_provider runtime-config| P[LLM-провайдер]
    P -->|ответ + meta| W
    W -->|POST /api/reviews parent_id| S
    S -->|insert ответ status=new| DB
    W -->|PATCH /api/reviews/{id} X-Worker-Token status=processed| S
    W -->|PATCH ответа status=processed| S
    W -->|PATCH /api/executions/{id} finish + steps| S
    S -->|execution_session ok/error + steps| DB
    W -->|state.json| ST[(state.json)]
    W -->|heartbeat.json| H[(heartbeat.json)]
```

### 🔀 4.2. Последовательность обработки одного отзыва

1. **Клиент** оставляет отзыв → `POST /api/reviews` → сайт сохраняет `status=new`.
2. **Воркер** (цикл `WORKER_POLL_INTERVAL`) → `GET /api/reviews?status=new` (серверный фильтр) → получает только новые.
3. **Execution start:** `POST /api/executions` (с `X-Worker-Token`) → `execution_sessions` `status=started`. Вся дальнейшая обработка отзыва обёрнута в эту сессию.
4. **Self-reply guard:** если `review.name == AI_AUTHOR_NAME` → шаг `mark_processed` (`reason=ai_authored`) → `PATCH status=processed` без генерации → finish сессии `ok`, переход к следующему. Это предотвращает бесконечный цикл (ответ воркера создаётся как `new`).
5. **`detect_tone`** (шаг 1) — словарный классификатор (без LLM): positive/negative/neutral по маркерам. Тон фиксируется в `step_metadata`.
6. **Telegram-уведомление** (шаг 2, опционально): если не `notified` и настроен токен → отправка; `mark_notified`. Иначе шаг `skipped`.
7. **Idempotency-проверка:** если `is_processed(id)` в `state.json` → сессия закрывается `ok` (шаг `mark_processed` `skipped`), пропуск дубля.
8. **`generate_response`** (шаг 3, `llm_call`) — `build_provider()` (runtime-config) + `load_system_prompt()` → `provider.generate()`. Возвращает `(text, meta)` где `meta={provider, model, latency_ms, tokens, fallback_reason}`. При `ProviderNotConfigured`/сбое/пустом ответе → `build_fallback_response` (`fallback_reason` фиксируется). `meta` пишется в `step_metadata`.
9. **`create_review`** (шаг 4, `persist_reply`) — `POST /api/reviews` с `parent_id`, `name=AI_AUTHOR_NAME`, `text=ответ` → сайт создаёт дочерний комментарий `status=new`.
10. **`update_review`** родителя → `PATCH status=processed, tone=...` (с `X-Worker-Token`).
11. **`update_review`** ответа → `PATCH status=processed` (чтобы воркер не подхватил его как новый на следующем цикле — двойная защита вместе с self-reply guard).
12. **`state.mark_processed`** (шаг 5) для родителя и ответа.
13. **Execution finish:** `PATCH /api/executions/{id}` — `status=ok`, `provider_key`/`model_name` из LLM-meta, `duration_ms`, все шаги одним пакетом. На исключение в любом шаге — `finish(status=error)` + `logger.exception`.
14. **`write_heartbeat`** → `heartbeat.json` (для Docker healthcheck).

---

## 🤖 5. Мультипровайдерность и runtime-config

### 🤖 5.1. Унификация

Все провайдеры унифицированы на **Chat Completions** (общий знаменатель), не на legacy `responses.create`. Абстракция — `ResponseProvider.generate(system_prompt, user_text) -> str`; для observability провайдер дополнительно раскрывает `name`, `model_name` и `last_usage` (токены последнего запроса, `None` если провайдер не вернул usage) — `processor.generate_response` собирает из них `meta` для execution-трассировки.

| Провайдер | Реализация | Ключ |
|-----------|-----------|------|
| OpenAI / «Свой» | `OpenAICompatibleProvider` (AsyncOpenAI, `base_url` из runtime) | `OPENAI_API_KEY` (.env) |
| GigaChat | `GigaChatProvider` → `GigaChatAdapter` (urllib, OAuth per-request) | `GIGACHAT_AUTH_KEY` (.env) |
| YandexGPT | `OpenAICompatibleProvider` + `x-folder-id` header + `<folder_id>` в модели | `YANDEX_API_KEY` (.env) |

### 🤖 5.2. Разделение секретов и runtime-параметров

| Где | Что | Кто меняет |
|-----|-----|-----------|
| `.env` | API-ключи (секреты) | Владелец/инженер (перед развёртыванием) |
| `config.json` (shared volume) | `provider`, `openai_model`, `openai_base_url`, `yandex_folder_id`, `system_prompt_override` | Оператор через `/admin` (без рестарта) |

> 📌 Ключи API **никогда** не попадают в `config.json`/браузер/`/admin`. `/admin` хранит только runtime-параметры.

### 🤖 5.3. Hot-reload (паттерн runtime-config, mtime-кеш)

`RuntimeConfig` (воркер) кеширует `config.json` по `st_mtime`. При каждом `get()` проверяется mtime; если изменился — перечитывается. Смена провайдера/модели/промпта через `/admin` применяется на **следующем цикле опроса** без рестарта воркера.

---

## 📝 6. Промпт

- **Файл:** `worker/prompts/v1/system.md` — единый SOT текста системного промпта (не хардкод).
- **Override:** если в `config.json` задан непустой `system_prompt_override` — используется он (применяется на следующем цикле).
- **Встроенный default** — на случай отсутствия файла (не должен случаться в образе).

---

## 📊 7. Наблюдаемость

Проект реализует **три независимых контура observability**, каждый со своей
зоной ответственности и носителем:

### 📊 7.1. Контур 1 — stdout-логирование (базис)

Централизованное логирование через `dictConfig` на старте обоих сервисов
(`site/app/core/logging.py`, `worker/logging_config.py`). Уровень задаётся
переменной `LOG_LEVEL` (по умолчанию `INFO`). Шумные логгеры `httpx`/`openai`
приглушены до `WARNING` (убирает спам опроса `GET /api/reviews?status=new`
каждые `WORKER_POLL_INTERVAL` секунд, ошибки остаются видны).

Формат: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`. Бизнес-события
сайта (`review.create`, `review.update`) и воркера (`Processing review id=...`)
пишутся сюда. Дешёвый базис для `docker compose logs`.

### 📊 7.2. Контур 2 — execution tracing (БД, обработка отзыва)

БД-персистентный контур обработки одного отзыва воркером. Каждая обработка =
`ExecutionSession` (статус/провайдер/модель/длительность), стадии пайплайна =
`ExecutionStep` с таймингом и `step_metadata` (для LLM-шага —
`provider`/`model`/`latency_ms`/`tokens`/`fallback_reason`).

Двухфазная запись через API сайта (у воркера нет БД-сессии — он отдельный
сервис с httpx): `POST /api/executions` (start, `status=started`) → воркер
собирает шаги в памяти с `perf_counter`-таймингом → `PATCH /api/executions/{id}`
(finish: `status=ok`/`error`, провайдер/модель, шаги одним пакетом). 2 HTTP-вызова
на отзыв. При падении воркера остаётся `started`-сессия (видна как зависшая —
диагностический признак). Просмотр: `/admin/executions` (read-only, demo допущен).

### 📊 7.3. Контур 3 — audit (БД, admin/security-события)

БД-персистентный контур admin/security-событий в `audit_logs`. Записывает
**кто, что, когда и откуда** сделал: `user_id`/`user_name`/`user_role`,
`action`, `resource_type`/`resource_id`, `ip_address`, `details` (JSON). События:

| Action | Когда | details |
|--------|-------|---------|
| `admin.login_success` / `admin.login_failed` | вход в `/admin` | ip, path |
| `admin.config_update` | сохранение runtime-config | provider/model/base_url, prompt_override_len, changed_keys (без текста промпта) |
| `admin.rbac_denied` | demo-попытка мутации → 403 | ip, path |
| `auth.worker_denied` | плохой/отсутствующий `X-Worker-Token` → 401 | ip, path |

Read-only-просмотры (`/admin/audit`, `/admin/executions`) **не аудируются** —
чтобы журнал не засорялся self-noise. Просмотр аудита: `/admin/audit` (read-only,
demo допущен). Секреты и полный текст промпт-override в `details` не пишутся.

### 📊 7.4. Сводная таблица сигналов

| Сигнал | Контур | Где | Назначение |
|--------|--------|-----|-----------|
| `GET /health` | — | сайт | Deployment Verification/Validation |
| `heartbeat.json` | — | воркер (`/service/data/`) | Docker healthcheck: mtime/`last_iteration_at` не старше `WORKER_HEALTHCHECK_MAX_AGE` |
| stdout-логи | 1 | оба сервиса | Этапы обработки (INFO), сбои провайдера (WARNING/EXCEPTION) |
| `execution_sessions` + `execution_steps` | 2 | БД (`/admin/executions`) | Трасса пайплайна + LLM-метрики каждого отзыва |
| `audit_logs` | 3 | БД (`/admin/audit`) | Журнал admin/security-событий |
| `state.json` | — | воркер | Идемпотентность (не observability) |

---

## 🚀 8. Развёртывание

Единый `docker-compose.yml`: `db` + `review-site` + `review-worker`, healthcheck на каждом сервисе, shared volume `runtime-config`. Подробно — [🚀 `DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md).

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта.
- [📋 `docs/SPEC.md`](SPEC.md) — продуктовая спецификация.
- [📋 `docs/IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — технический план.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты HTTP API.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры LLM-провайдеров.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность и демо-RBAC.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание с нуля.
- [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) — отчёт воспроизводимости.
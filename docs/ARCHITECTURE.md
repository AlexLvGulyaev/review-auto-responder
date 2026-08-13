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

---

## 🔀 4. Путь данных (data flow)

### 🔀 4.1. Схема

```mermaid
flowchart TD
    C([Клиент]) -->|POST /api/reviews| S[review-site]
    S -->|insert status=new| DB[(PostgreSQL)]
    W[review-worker] -->|GET /api/reviews?status=new| S
    S -->|только new| W
    W -->|detect_tone словарь| W
    W -->|Telegram notify опционально| T([Оператор])
    W -->|build_provider runtime-config| P[LLM-провайдер]
    P -->|ответ| W
    W -->|POST /api/reviews parent_id| S
    S -->|insert ответ status=new| DB
    W -->|PATCH /api/reviews/{id} X-Worker-Token status=processed| S
    W -->|PATCH ответа status=processed| S
    W -->|state.json| ST[(state.json)]
    W -->|heartbeat.json| H[(heartbeat.json)]
```

### 🔀 4.2. Последовательность обработки одного отзыва

1. **Клиент** оставляет отзыв → `POST /api/reviews` → сайт сохраняет `status=new`.
2. **Воркер** (цикл `WORKER_POLL_INTERVAL`) → `GET /api/reviews?status=new` (серверный фильтр) → получает только новые.
3. **Self-reply guard:** если `review.name == AI_AUTHOR_NAME` → `PATCH status=processed` без генерации, переход к следующему. Это предотвращает бесконечный цикл (ответ воркера создаётся как `new`).
4. **`detect_tone`** — словарный классификатор (без LLM): positive/negative/neutral по маркерам.
5. **Telegram-уведомление** (опционально): если не `notified` и настроен токен → отправка; `mark_notified`.
6. **Idempotency-проверка:** если `is_processed(id)` в `state.json` → пропуск (дубль в окне до подтверждения сайтом).
7. **`generate_response`** — `build_provider()` (runtime-config) + `load_system_prompt()` (файл или override) → `provider.generate()`. При `ProviderNotConfigured`/сбое/пустом ответе → `build_fallback_response` (словарные шаблоны по тону).
8. **`create_review`** — `POST /api/reviews` с `parent_id`, `name=AI_AUTHOR_NAME`, `text=ответ` → сайт создаёт дочерний комментарий `status=new`.
9. **`update_review`** родителя → `PATCH status=processed, tone=...` (с `X-Worker-Token`).
10. **`update_review`** ответа → `PATCH status=processed` (чтобы воркер не подхватил его как новый на следующем цикле — двойная защита вместе с self-reply guard).
11. **`state.mark_processed`** для родителя и ответа.
12. **`write_heartbeat`** → `heartbeat.json` (для Docker healthcheck).

---

## 🤖 5. Мультипровайдерность и runtime-config

### 🤖 5.1. Унификация

Все провайдеры унифицированы на **Chat Completions** (общий знаменатель), не на legacy `responses.create`. Абстракция — `ResponseProvider.generate(system_prompt, user_text) -> str`.

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

| Сигнал | Где | Назначение |
|--------|-----|-----------|
| `GET /health` | сайт | Deployment Verification/Validation |
| `heartbeat.json` | воркер (`/service/data/`) | Docker healthcheck: mtime/`last_iteration_at` не старше `WORKER_HEALTHCHECK_MAX_AGE` |
| Логи | оба сервиса | Этапы обработки (INFO), сбои провайдера (WARNING/EXCEPTION) |
| `state.json` | воркер | Идемпотентность (не для мониторинга) |

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
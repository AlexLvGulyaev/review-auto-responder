# 📋 Review Auto Responder · IMPLEMENTATION_PLAN

**Проект:** review-auto-responder
**Дата:** 2026-08-13
**Статус:** ✅ Реализован. Технический план доработанной версии на базе legacy-репозиториев-референсов (`github.com/MrGAN12009/worker_ai`, `app_test_2803`). Все этапы выполнены, Deployment Validation 17/17 PASS.

---

## 🎯 1. Архитектура решения

```mermaid
flowchart TD
    subgraph Site["Сайт отзывов (review-site)"]
        U["Клиент · Web UI"] -->|POST /api/reviews| API["FastAPI · api/routes.py"]
        API --> DB[("PostgreSQL · reviews")]
        API -->|GET /api/reviews?status=new| W
        OP["Оператор-настройщик"] -->|token-cookie| ADM["/admin · api/admin.py"]
        ADM -->|write| CFG[("config.json · shared volume")]
    end
    subgraph Worker["Обработчик (review-worker)"]
        CFG -->|mtime hot-reload| RC["runtime_config.py"]
        W["worker.py · основной цикл"] -->|fetch_new_reviews| CL["client.py · HTTP-транспорт"]
        W -->|detect_tone| PR["processor.py · словарный классификатор"]
        W -->|generate_response| PRV["providers/ · фабрика по runtime provider"]
        PRV -->|промпт| PL["prompt_loader.py · prompts/v1/system.md + override"]
        RC --> PRV
        RC --> PL
        W -->|уведомление| TG["telegram_bot.py"]
        W -->|идемпотентность| ST["state.py · state.json"]
        W -->|heartbeat| HB["data/heartbeat.json"]
        W -->|execution-tracing| EX["POST/PATCH /api/executions · API сайта"]
    end
    CL -->|PATCH /api/reviews/{id} + X-Worker-Token| API
    CL -->|POST /api/reviews · дочерний ответ| API
    PRV -.fallback.-> PR
```

Путь данных (детально — в `docs/ARCHITECTURE.md`):

1. Клиент пишет отзыв → `POST /api/reviews` → строка `Review` `status=new` в PostgreSQL.
2. `worker.py` опрашивает `GET /api/reviews?status=new` (`client.py`) каждые `WORKER_POLL_INTERVAL` сек.
3. На каждый новый: обёртка в execution-сессию (`POST /api/executions`) → `processor.detect_tone` (словарь) → `telegram_bot` (опционально) → `processor.generate_response` (возвращает `(text, meta)`) → `providers/` (LLM) или fallback.
4. `client.create_review` постит ответ дочерним комментарием; `client.update_review` (PATCH + `X-Worker-Token`) → `status=processed` для родителя и ответа.
5. `state.py` фиксирует notified/processed; `is_ai_authored` + mark-processed защищают от self-reply.
6. `PATCH /api/executions/{id}` закрывает сессию (`ok`/`error`, провайдер/модель, шаги с LLM-метаданными).

---

## 🧩 2. Состав компонентов

### 2.1. Сайт отзывов (`site/`)

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Точка входа | `app/main.py` | FastAPI app, lifespan (idempotent init схемы), router |
| Роуты | `app/api/routes.py` | `GET /`, `GET /api/reviews` (+`?status=new`), `POST /api/reviews`, `PATCH /api/reviews/{id}`, `GET /health` |
| Админка | `app/api/admin.py` | Демо-RBAC: два токена (admin/demo), role-based guard на backend (`AdminIdentity` role admin/demo, `admin_auth` чтение + `require_admin` мутация → 403 для demo), login/logout по cookie; `GET/POST /admin` пишет `config.json` |
| Execution-трейсы | `app/api/executions.py` | `POST /api/executions` (start), `PATCH /api/executions/{id}` (finish) — воркер пишет трассы под `X-Worker-Token` |
| Admin-трейсы | `app/api/admin_executions.py` | `GET /admin/executions`, `GET /admin/executions/{id}` — read-only просмотр (demo допущен) |
| Audit-API | `app/api/audit.py` | `GET /admin/audit`, `GET /admin/audit/{id}` — read-only просмотр журнала (demo допущен) |
| Worker-auth | `app/api/worker_auth.py` | `require_worker_token` → 401 + audit `auth.worker_denied` при плохом/отсутствующем токене |
| Audit-сервис | `app/services/audit.py` | `AuditService.log_audit` + `client_ip` (X-Forwarded-For → X-Real-IP → client.host) |
| Logging | `app/core/logging.py` | `configure_logging()` через dictConfig, уровень `LOG_LEVEL` |
| Схемы | `app/schemas.py` | `ReviewCreate`, `ReviewRead`, `ReviewUpdate`, `RuntimeConfigUpdate`, execution/audit схемы (Pydantic) |
| Модели БД | `app/models/review.py`, `execution.py`, `audit.py` | `Review` (самоссылка), `ExecutionSession`+`ExecutionStep`, `AuditLog` |
| Сессия БД | `app/db/session.py` | async engine, session factory, `get_db_session` |
| Базовый класс | `app/db/base.py` | `DeclarativeBase` |
| Конфиг | `app/config.py` | Pydantic-settings из `.env`, `database_url` computed, `admin_token`, `admin_demo_token`, `admin_auth_enabled`, `runtime_config_path`, `log_level` |
| Шаблон | `app/templates/index.html` | Web UI, опрос каждые 5с, дерево комментариев |
| Админ-шаблоны | `app/templates/admin.html`, `admin_login.html`, `executions.html`, `execution_detail.html`, `audit.html`, `audit_detail.html` | Форма runtime-config + панели observability (read-only) + форма входа по токену |
| Dockerfile | `site/Dockerfile` | python:3.12-slim, uvicorn |
| Требования | `site/requirements.txt` | fastapi, uvicorn, sqlalchemy, asyncpg, pydantic, jinja2, python-multipart |

### 2.2. Обработчик (`worker/`)

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Точка входа | `worker.py` | Основной цикл, `wait_for_site`, `process_new_reviews` (обёртка каждого отзыва в execution-сессию), heartbeat |
| HTTP-клиент | `client.py` | `check_site`, `fetch_new_reviews` (через `?status=new`), `create_review`, `update_review`, `start_execution`, `finish_execution` |
| Классификатор | `processor.py` | `detect_tone` (словарь маркеров), `build_fallback_response`, `generate_response` → `(text, meta)` где `meta={provider, model, latency_ms, tokens, fallback_reason}` |
| Провайдеры | `providers/base.py` | `ResponseProvider` ABC: `async generate(system, user) -> str`, `name`/`model_name`/`last_usage` для observability |
| OpenAI-совместимый | `providers/openai_provider.py` | OpenAI SDK Chat Completions; `base_url` из runtime-config (любой OpenAI-compatible endpoint) |
| GigaChat | `providers/gigachat_provider.py` | OAuth-адаптер, async-обёртка через `asyncio.to_thread` |
| Фабрика | `providers/factory.py` | Выбор провайдера по `runtime.get("provider")` (openai/gigachat, не env) |
| Runtime-config | `runtime_config.py` | mtime-кеш `config.json` из shared volume + `threading.Lock`; `get(key)` |
| Промпт | `prompt_loader.py` | Чтение `system_prompt.md` из shared volume (файл-SOT, mtime-кеш); fallback на вшитый `prompts/v1/system.md` |
| Промпт-файл | `prompts/v1/system.md` | Начальный default для bootstrap (копируется в shared volume при первом запуске) |
| Состояние | `state.py` | `state.json`: `notified_review_ids`, `processed_review_ids` |
| Telegram | `telegram_bot.py` | `send_new_review_notification` (опционально) |
| Модели | `models.py` | `RemoteReview`, `ReviewCreatePayload`, `ReviewUpdatePayload`, `ReviewStatus`, `ReviewTone` |
| Конфиг | `config.py` | Pydantic-settings из `.env` (секреты + пути); `runtime_config_path`, `log_level` |
| Logging | `logging_config.py` | `configure_logging()` через dictConfig + приглушённые `httpx`/`openai` |
| Dockerfile | `worker/Dockerfile` | python:3.12-slim, `python worker.py`, healthcheck по heartbeat |
| Требования | `worker/requirements.txt` | httpx, openai, pydantic, pydantic-settings |

### 2.3. Оркестрация

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Единый compose | `docker-compose.yml` | `db` + `review-site` + `review-worker`, healthcheck'и, общий `WORKER_API_TOKEN`, shared volume `runtime-config`, `LOG_LEVEL` |
| Переменные | `.env.example` | Все переменные обоих сервисов с placeholder'ами (`ADMIN_TOKEN`, `ADMIN_DEMO_TOKEN`, `WORKER_API_TOKEN`, `LOG_LEVEL`, ключи провайдеров) |

---

## 📐 3. Модель данных

### 3.1. `reviews` — отзыв/комментарий (сайт, PostgreSQL)

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `Integer` PK | Идентификатор |
| `parent_id` | `Integer` FK→`reviews.id` \| null | Родитель (для вложенных комментариев) |
| `name` | `String(255)` \| null | Имя автора |
| `text` | `Text` | Текст отзыва |
| `status` | `Enum(new, processed)` | Статус обработки; default `new` |
| `response` | `Text` \| null | Зарезервировано (legacy-поле; ответ публикуется дочерним комментарием) |
| `tone` | `String(32)` \| null | Тон: positive/negative/neutral (ставит обработчик) |
| `created_at` | `DateTime(tz)` | Время создания |

### 3.2. `execution_sessions` — трасса обработки отзыва (observability, контур 2)

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `Integer` PK | Идентификатор сессии |
| `review_id` | `Integer` FK→`reviews.id` (SET NULL) \| null | Обрабатываемый отзыв |
| `status` | `String(32)` | `started`/`ok`/`error` |
| `route` | `String(64)` | Маршрут (`review_processing`) |
| `provider_key` | `String(64)` \| null | LLM-провайдер |
| `model_name` | `String(128)` \| null | Имя модели |
| `duration_ms` | `Integer` \| null | Длительность обработки |
| `started_at` / `finished_at` | `DateTime(tz)` | Время старта/финала |
| `execution_metadata` | `JSONB` | Метаданные сессии (`reply_id`, `error`, ...) |

### 3.3. `execution_steps` — стадии пайплайна

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `Integer` PK | Идентификатор шага |
| `execution_session_id` | `Integer` FK→`execution_sessions.id` (CASCADE) | Родительская сессия |
| `stage_name` | `String(64)` | `detect_tone`/`telegram`/`llm_call`/`persist_reply`/`mark_processed` |
| `step_order` | `Integer` | Порядок шага |
| `status` | `String(32)` | `ok`/`error`/`skipped` |
| `started_at` / `finished_at` | `DateTime(tz)` \| null | Тайминг шага |
| `duration_ms` | `Integer` \| null | Длительность шага |
| `step_metadata` | `JSONB` | Для `llm_call`: `{provider, model, latency_ms, tokens, fallback_reason}` |

### 3.4. `audit_logs` — журнал admin/security-событий (observability, контур 3)

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `Integer` PK | Идентификатор записи |
| `user_id` / `user_name` / `user_role` | `String` \| null | Кто совершил действие |
| `action` | `String(64)` | `admin.login_success`/`admin.login_failed`/`admin.config_update`/`admin.rbac_denied`/`auth.worker_denied` |
| `resource_type` / `resource_id` | `String` \| null | Над чем совершено |
| `ip_address` | `String(45)` \| null | Откуда (X-Forwarded-For → X-Real-IP → client.host) |
| `details` | `JSONB` | Контекст (без секретов и полных промптов) |
| `created_at` | `DateTime(tz)` | Время события |

### 3.5. `state.json` — локальное состояние обработчика

| Поле | Тип | Описание |
|------|-----|----------|
| `notified_review_ids` | `list[int]` | Отзывы, по которым уже отправлено Telegram-уведомление |
| `processed_review_ids` | `list[int]` | Отзывы, по которым уже сгенерирован ответ (defensive guard) |

### 3.6. `heartbeat.json` — healthcheck обработчика

| Поле | Тип | Описание |
|------|-----|----------|
| `last_iteration_at` | `str` (ISO) | Метка времени последней итерации цикла |
| `target_site_url` | `str` | Целевой сайт (для диагностики) |

### 3.7. `config.json` — runtime-config (shared volume, пишется `/admin`)

| Поле | Тип | Описание |
|------|-----|----------|
| `provider` | `str` | Активный провайдер: `openai`/`gigachat` |
| `openai_model` | `str` | Модель OpenAI |
| `openai_base_url` | `str` | base_url OpenAI / OpenAI-compatible endpoint |
| `gigachat_model` | `str` | Модель GigaChat |

Промпт хранится отдельно — файл `system_prompt.md` на том же shared volume (файл-SOT), не поле `config.json`.

**Секреты (`OPENAI_API_KEY`, `GIGACHAT_AUTH_KEY`) в `config.json` НЕ хранятся** — только в `.env` обработчика. `/admin` редактирует runtime-параметры, не ключи.

> 📌 Таблицы observability создаются `Base.metadata.create_all` в lifespan сайта (без Alembic) — idempotent для существующей БД.

---

## 🔌 4. Интеграции

| Интеграция | Контракт | SOT |
|------------|----------|-----|
| Сайт ↔ обработчик | `GET /api/reviews?status=new`, `POST /api/reviews`, `PATCH /api/reviews/{id}` + `X-Worker-Token` | `docs/API_CONTRACT.md` + код сайта |
| Воркер → execution-tracing | `POST /api/executions` (start), `PATCH /api/executions/{id}` (finish) + `X-Worker-Token` | `docs/API_CONTRACT.md` + код `executions.py` |
| `/admin` → обработчик | Сайт пишет `config.json` в shared volume; обработчик читает по mtime (hot-reload, без рестарта) | `docs/ARCHITECTURE.md` + код `runtime_config.py` |
| OpenAI | Chat Completions (`/v1/chat/completions`), `Authorization: Bearer` | `docs/EXTERNAL_PROVIDERS.md` |
| GigaChat | OAuth-обмен auth_key→access_token (`/oauth`), `/chat/completions`, сертификат Минцифры | адаптер `gigachat_provider.py` (SOT — код + доки GigaChat) |
| Telegram Bot API | `POST /bot<token>/sendMessage` | код `telegram_bot.py` + доки Telegram |

**Унификация вызова:** legacy использовал OpenAI `responses.create`. Доработка переводит все провайдеры на Chat Completions — общий знаменатель (GigaChat — OpenAI-compatible Chat Completions; OpenAI поддерживает оба). Это сознательная, документированная дивергенция от legacy ради единой абстракции.

---

## 📅 5. План реализации

| # | Задача | Артефакты |
|---|--------|-----------|
| 1 | Каркас `site/` на базе `app_test_2803` + `?status=new` + `/health` | `site/app/**`, `site/Dockerfile`, `site/requirements.txt` |
| 2 | Web-`/admin` на сайте: демо-RBAC (`AdminIdentity`, два токена, `admin_auth`/`require_admin`, login/logout cookie), `templates/admin.html` + `admin_login.html`, writer `config.json` в shared volume | `site/app/api/admin.py`, `site/app/templates/admin*.html` |
| 3 | Каркас `worker/` на базе `worker_ai`: `worker.py`, `client.py` (через `?status=new`), `state.py`, `telegram_bot.py`, `models.py`, `config.py` | `worker/**` (без провайдеров пока) |
| 4 | `runtime_config.py` — mtime-кеш `config.json` из shared volume | `worker/runtime_config.py` |
| 5 | Мультипровайдерность: `providers/base.py`, `openai_provider.py`, `gigachat_provider.py` (OAuth-адаптер), `factory.py` (по `runtime.get("provider")`) | `worker/providers/**` |
| 6 | Промпт в файле: `prompt_loader.py` (override из runtime), `prompts/v1/system.md`; `processor.generate_response` делегирует провайдеру + fallback | `worker/prompts/**`, `worker/processor.py`, `worker/prompt_loader.py` |
| 7 | Heartbeat для healthcheck | `worker/worker.py`, `worker/Dockerfile` healthcheck |
| 8 | Единый `docker-compose.yml` + `.env.example` (shared volume `runtime-config`) | `docker-compose.yml`, `.env.example` |
| 9 | Документация: `ARCHITECTURE.md` (путь данных), `API_CONTRACT.md`, `SECURITY_NOTES.md`, `DEPLOYMENT_GUIDE.md`, `EXTERNAL_PROVIDERS.md` | `docs/**` |
| 10 | Локальная сборка + верификация (3 отзыва разной тональности; смена провайдера через `/admin` без рестарта) | `docs/TESTING.md` |
| 11 | Deployment Validation в чистом окружении | `docs/DEPLOYMENT_VALIDATION_REPORT.md` |
| 12 | Публичный репозиторий + README + живое демо | `README.md` |
| 13 | Observability: три контура (stdout-логирование, execution-tracing, аудит) + панели `/admin/executions`, `/admin/audit` | `site/app/core/`, `site/app/models/execution.py`, `audit.py`, `site/app/services/audit.py`, `site/app/api/executions.py`, `audit.py`, `admin_executions.py`, `worker/logging_config.py`, шаблоны |

---

## ✅ 6. Критерии готовности

- [x] Единый `docker compose up --build -d` поднимает `db` + `review-site` + `review-worker`; сайт отвечает, обработчик опрашивает.
- [x] `GET /health` сайта → 200; healthcheck обработчика (heartbeat) → healthy.
- [x] `GET /api/reviews?status=new` отдаёт только новые отзывы.
- [x] Три отзыва (позитивный/негативный/нейтральный): тон определён, ответ сгенерирован, статус `processed`.
- [x] `provider` (через `/admin`) = openai/gigachat — ответ генерируется через выбранный провайдер; при сбое/нет ключа — fallback.
- [x] `/admin` меняет провайдер/модель/промпт в runtime — применяется на следующем цикле опроса без рестарта обработчика.
- [x] Демо-RBAC: `ADMIN_DEMO_TOKEN` → чтение `/admin` разрешено, POST `/admin` → 403 (backend guard); `ADMIN_TOKEN` → мутации разрешены.
- [x] Промпт — файл-SOT на shared volume (`system_prompt.md`, bootstrap из вшитого `prompts/v1/system.md`); правка через `/admin` перезаписывает файл и влияет на ответ без правки кода.
- [x] Секреты (ключи API) только в `.env`; `config.json` содержит только runtime-параметры.
- [x] Self-reply предотвращён (обработчик не отвечает на собственные ответы).
- [x] Telegram-уведомление при настроенном токене; пропуск без него.
- [x] Секреты в `.env` (не в репозитории); `.env.example` с placeholder'ами.
- [x] Deployment Validation пройдена в чистом окружении (отчёт 17/17 PASS).
- [x] Observability: stdout-логирование (`LOG_LEVEL`), execution-tracing (`/admin/executions` с LLM-метриками), аудит (`/admin/audit`).
- [x] Публичная документация самодостаточна (нет ссылок на документы, отсутствующие в репозитории).

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта.
- [📊 `docs/PROJECT_STATE.md`](PROJECT_STATE.md) — паспорт состояния.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура и путь данных.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты интеграций.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание с нуля.
- [🔐 `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность и демо-RBAC.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — LLM-провайдеры.
- [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) — отчёт воспроизводимости.
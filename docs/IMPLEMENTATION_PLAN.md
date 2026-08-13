# 📋 Review Auto Responder · IMPLEMENTATION_PLAN

**Проект:** review-auto-responder
**Дата:** 2026-08-13
**Статус:** plan. Технический план доработанной версии на базе legacy преподавателя. Разработка начинается после утверждения плана.

---

## 🎯 1. Архитектура решения

```mermaid
flowchart TD
    subgraph Site["Сайт отзывов (review-site)"]
        U["Клиент · Web UI"] -->|POST /api/reviews| API["FastAPI · api/routes.py"]
        API --> DB[("PostgreSQL · reviews")]
        API -->|GET /api/reviews?status=new| W
        OP["Оператор-настройщик"] -->|HTTP Basic| ADM["/admin · api/admin.py"]
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
    end
    CL -->|PATCH /api/reviews/{id} + X-Worker-Token| API
    CL -->|POST /api/reviews · дочерний ответ| API
    PRV -.fallback.-> PR
```

Путь данных (детально — в `docs/ARCHITECTURE.md`):

1. Клиент пишет отзыв → `POST /api/reviews` → строка `Review` `status=new` в PostgreSQL.
2. `worker.py` опрашивает `GET /api/reviews?status=new` (`client.py`) каждые `WORKER_POLL_INTERVAL` сек.
3. На каждый новый: `processor.detect_tone` (словарь) → `telegram_bot` (опционально) → `processor.generate_response` → `providers/` (LLM) или fallback.
4. `client.create_review` постит ответ дочерним комментарием; `client.update_review` (PATCH + `X-Worker-Token`) → `status=processed` для родителя и ответа.
5. `state.py` фиксирует notified/processed; `is_ai_authored` + mark-processed защищают от self-reply.

---

## 🧩 2. Состав компонентов

### 2.1. Сайт отзывов (`site/`)

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Точка входа | `app/main.py` | FastAPI app, lifespan (idempotent init схемы), router |
| Роуты | `app/api/routes.py` | `GET /`, `GET /api/reviews` (+`?status=new`), `POST /api/reviews`, `PATCH /api/reviews/{id}`, `GET /health` |
| Админка | `app/api/admin.py` | Демо-RBAC: стандартный демо-сценарий APL — два токена (admin/demo), role-based guard на backend (`AdminIdentity` role admin/demo, `admin_auth` чтение + `require_admin` мутация → 403 для demo), login/logout по cookie; `GET/POST /admin` пишет `config.json` |
| Схемы | `app/schemas.py` | `ReviewCreate`, `ReviewRead`, `ReviewUpdate`, `RuntimeConfigUpdate` (Pydantic) |
| Модель БД | `app/models/review.py` | `Review` (самоссылка parent_id, status, tone, response) |
| Сессия БД | `app/db/session.py` | async engine, session factory, `get_db_session` |
| Базовый класс | `app/db/base.py` | `DeclarativeBase` |
| Конфиг | `app/config.py` | Pydantic-settings из `.env`, `database_url` computed, `admin_token`, `admin_demo_token`, `admin_auth_enabled`, `runtime_config_path` |
| Шаблон | `app/templates/index.html` | Web UI, опрос каждые 5с, дерево комментариев |
| Админ-шаблоны | `app/templates/admin.html`, `admin_login.html` | Форма runtime-config (бейдж demo, disabled save) + форма входа по токену |
| Dockerfile | `site/Dockerfile` | python:3.12-slim, uvicorn |
| Требования | `site/requirements.txt` | fastapi, uvicorn, sqlalchemy, asyncpg, pydantic, jinja2 |

### 2.2. Обработчик (`worker/`)

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Точка входа | `worker.py` | Основной цикл, `wait_for_site`, `process_new_reviews`, heartbeat |
| HTTP-клиент | `client.py` | `check_site`, `fetch_new_reviews` (через `?status=new`), `create_review`, `update_review` |
| Классификатор | `processor.py` | `detect_tone` (словарь маркеров), `build_fallback_response`, `generate_response` (делегирует провайдеру) |
| Провайдеры | `providers/base.py` | `ResponseProvider` ABC: `async generate(system, user) -> str` |
| OpenAI-совместимый | `providers/openai_provider.py` | OpenAI SDK Chat Completions; работает для openai/yandex/custom (base_url + default_headers для yandex `x-folder-id`) |
| GigaChat | `providers/gigachat_provider.py` | OAuth-адаптер (переиспользован из ранее разработанного в лаборатории), async-обёртка через `asyncio.to_thread` |
| Фабрика | `providers/factory.py` | Выбор провайдера по `runtime.get("provider")` (не env) |
| Runtime-config | `runtime_config.py` | mtime-кеш `config.json` из shared volume + `threading.Lock` (паттерн runtime-config, mtime-кеш); `get(key)` |
| Промпт | `prompt_loader.py` | Загрузка `prompts/v1/system.md`; override из `runtime.get("system_prompt_override")`; интерполяция `{{provider_attribution}}` |
| Промпт-файл | `prompts/v1/system.md` | Системный промпт генерации ответа (единый SOT текста; override через `/admin`) |
| Состояние | `state.py` | `state.json`: `notified_review_ids`, `processed_review_ids` |
| Telegram | `telegram_bot.py` | `send_new_review_notification` (опционально) |
| Модели | `models.py` | `RemoteReview`, `ReviewCreatePayload`, `ReviewUpdatePayload`, `ReviewStatus`, `ReviewTone` |
| Конфиг | `config.py` | Pydantic-settings из `.env` (секреты + пути); `runtime_config_path` |
| Dockerfile | `worker/Dockerfile` | python:3.12-slim, `python worker.py`, healthcheck по heartbeat |
| Требования | `worker/requirements.txt` | httpx, openai, pydantic, pydantic-settings |

### 2.3. Оркестрация

| Компонент | Файл | Назначение |
|-----------|------|------------|
| Единый compose | `docker-compose.yml` | `db` + `review-site` + `review-worker`, healthcheck'и, общий `WORKER_API_TOKEN`, shared volume `runtime-config` |
| Переменные | `.env.example` | Все переменные обоих сервисов с placeholder'ами (`ADMIN_TOKEN`, `WORKER_API_TOKEN`, ключи провайдеров) |

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

### 3.2. `state.json` — локальное состояние обработчика

| Поле | Тип | Описание |
|------|-----|----------|
| `notified_review_ids` | `list[int]` | Отзывы, по которым уже отправлено Telegram-уведомление |
| `processed_review_ids` | `list[int]` | Отзывы, по которым уже сгенерирован ответ (defensive guard) |

### 3.3. `heartbeat.json` — healthcheck обработчика

| Поле | Тип | Описание |
|------|-----|----------|
| `last_iteration_at` | `str` (ISO) | Метка времени последней итерации цикла |
| `target_site_url` | `str` | Целевой сайт (для диагностики) |

### 3.4. `config.json` — runtime-config (shared volume, пишется `/admin`)

| Поле | Тип | Описание |
|------|-----|----------|
| `provider` | `str` | Активный провайдер: `openai`/`gigachat`/`yandex`/`custom` |
| `openai_model` | `str` | Модель (для yandex — `gpt://<folder_id>/yandexgpt/latest`) |
| `openai_base_url` | `str` | base_url (для custom; для openai/yandex — пресет) |
| `yandex_folder_id` | `str` | folder_id Yandex (runtime-параметр, не секрет) |
| `system_prompt_override` | `str` \| null | Override промпта; null → используется `prompts/v1/system.md` |

**Секреты (`OPENAI_API_KEY`, `GIGACHAT_AUTH_KEY`, `YANDEX_API_KEY`) в `config.json` НЕ хранятся** — только в `.env` обработчика. `/admin` редактирует runtime-параметры, не ключи.

---

## 🔌 4. Интеграции

| Интеграция | Контракт | SOT |
|------------|----------|-----|
| Сайт ↔ обработчик | `GET /api/reviews?status=new`, `POST /api/reviews`, `PATCH /api/reviews/{id}` + `X-Worker-Token` | `docs/API_CONTRACT.md` + код сайта |
| `/admin` → обработчик | Сайт пишет `config.json` в shared volume; обработчик читает по mtime (hot-reload, без рестарта) | `docs/ARCHITECTURE.md` + код `runtime_config.py` |
| OpenAI | Chat Completions (`/v1/chat/completions`), `Authorization: Bearer` | `docs/EXTERNAL_PROVIDERS.md` (переиспользован из ранее разработанного в лаборатории) |
| GigaChat | OAuth-обмен auth_key→access_token (`/oauth`), `/chat/completions`, сертификат Минцифры | адаптер `gigachat_provider.py` (SOT — код + доки GigaChat) |
| YandexGPT | `/chat/completions`, Bearer + `x-folder-id`, модель `gpt://<folder_id>/yandexgpt/latest` | `docs/EXTERNAL_PROVIDERS.md` |
| Telegram Bot API | `POST /bot<token>/sendMessage` | код `telegram_bot.py` + доки Telegram |

**Унификация вызова:** legacy использовал OpenAI `responses.create`. Доработка переводит все провайдеры на Chat Completions — общий знаменатель (GigaChat/Yandex — OpenAI-compatible Chat Completions; OpenAI поддерживает оба). Это сознательная, документированная дивергенция от legacy ради единой абстракции.

---

## 📅 5. План реализации

| # | Задача | Артефакты |
|---|--------|-----------|
| 1 | Каркас `site/` на базе `app_test_2803` + `?status=new` + `/health` | `site/app/**`, `site/Dockerfile`, `site/requirements.txt` |
| 2 | Web-`/admin` на сайте: демо-RBAC (`AdminIdentity`, два токена, `admin_auth`/`require_admin`, login/logout cookie), `templates/admin.html` + `admin_login.html`, writer `config.json` в shared volume | `site/app/api/admin.py`, `site/app/templates/admin*.html` |
| 3 | Каркас `worker/` на базе `worker_ai`: `worker.py`, `client.py` (через `?status=new`), `state.py`, `telegram_bot.py`, `models.py`, `config.py` | `worker/**` (без провайдеров пока) |
| 4 | `runtime_config.py` — mtime-кеш `config.json` из shared volume (паттерн runtime-config, mtime-кеш) | `worker/runtime_config.py` |
| 5 | Мультипровайдерность: `providers/base.py`, `openai_provider.py`, `gigachat_provider.py` (переиспользование адаптера), `factory.py` (по `runtime.get("provider")`) | `worker/providers/**` |
| 6 | Промпт в файле: `prompt_loader.py` (override из runtime), `prompts/v1/system.md`; `processor.generate_response` делегирует провайдеру + fallback | `worker/prompts/**`, `worker/processor.py`, `worker/prompt_loader.py` |
| 7 | Heartbeat для healthcheck | `worker/worker.py`, `worker/Dockerfile` healthcheck |
| 8 | Единый `docker-compose.yml` + `.env.example` (shared volume `runtime-config`) | `docker-compose.yml`, `.env.example` |
| 9 | Документация: `ARCHITECTURE.md` (путь данных), `API_CONTRACT.md`, `SECURITY_NOTES.md`, `DEPLOYMENT_GUIDE.md`, `EXTERNAL_PROVIDERS.md` | `docs/**` |
| 10 | Локальная сборка + верификация (3 отзыва разной тональности; смена провайдера через `/admin` без рестарта) | `docs/TESTING.md` |
| 11 | Deployment Validation в чистом окружении | `docs/DEPLOYMENT_VALIDATION_REPORT.md` |
| 12 | Публичный репозиторий + README + отчёт ДЗ + письмо куратору | `README.md` |

---

## ✅ 6. Критерии готовности

- [ ] Единый `docker compose up --build -d` поднимает `db` + `review-site` + `review-worker`; сайт отвечает, обработчик опрашивает.
- [ ] `GET /health` сайта → 200; healthcheck обработчика (heartbeat) → healthy.
- [ ] `GET /api/reviews?status=new` отдаёт только новые отзывы.
- [ ] Три отзыва (позитивный/негативный/нейтральный): тон определён, ответ сгенерирован, статус `processed`.
- [ ] `WORKER_PROVIDER` = openai/gigachat/yandex — ответ генерируется через выбранный провайдер; при сбое/нет ключа — fallback.
- [ ] `/admin` меняет провайдер/модель/промпт в runtime — применяется на следующем цикле опроса без рестарта обработчика.
- [ ] Демо-RBAC: `ADMIN_DEMO_TOKEN` → чтение `/admin` разрешено, POST `/admin` → 403 (backend guard); `ADMIN_TOKEN` → мутации разрешены.
- [ ] Промпт читается из `prompts/v1/system.md` (правка файла влияет на ответ без правки кода); override через `/admin`.
- [ ] Секреты (ключи API) только в `.env`; `config.json` содержит только runtime-параметры.
- [ ] Self-reply предотвращён (обработчик не отвечает на собственные ответы).
- [ ] Telegram-уведомление при настроенном токене; пропуск без него.
- [ ] Секреты в `.env` (не в репозитории); `.env.example` с placeholder'ами.
- [ ] Deployment Validation пройдена в чистом окружении (отчёт PASS).
- [ ] Публичная документация самодостаточна (нет ссылок на внутренние артефакты APL).

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта (предстоит).
- [📊 `docs/PROJECT_STATE.md`](PROJECT_STATE.md) — паспорт состояния.
- [📋 `docs/SPEC.md`](SPEC.md) — продуктовая спецификация.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура и путь данных (предстоит).
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты интеграций (предстоит).
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание с нуля (предстоит).
- [🔐 `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность (предстоит).
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — LLM-провайдеры (предстоит).
# 📊 Review Auto Responder · PROJECT_STATE

**Проект:** review-auto-responder
**Дата создания:** 2026-08-13
**Последнее обновление:** 2026-08-13
**Статус:** ✅ Портфельный актив. Реализован, прошёл Deployment Validation (17/17 PASS), опубликован как публичный репозиторий с живым демо.

---

## 🎯 1. Project Summary

Автономный ассистент, который 24/7 собирает новые отзывы с сайта, определяет тональность, генерирует ответ нейросетью и шлёт уведомление оператору в Telegram. Связка «парсер + автономная обработка» — универсальный паттерн (отзывы, отклики на фриланс-заказы, любые задачи «сбор + AI-обработка 24/7»).

Проект состоит из двух сервисов:

1. **Сайт отзывов** (на базе legacy `app_test_2803`) — FastAPI + PostgreSQL 16, модель `Review` с самоссылкой `parent_id` (вложенные комментарии), поля `status` (new/processed), `tone`, `response`. Эндпоинты: `GET /`, `GET/POST /api/reviews`, `PATCH /api/reviews/{id}`.
2. **Ассистент-обработчик** (на базе legacy `worker_ai`) — async-поллер: каждые N секунд забирает с сайта отзывы со `status=new`, определяет тон, генерирует ответ, пишет ответ обратно (дочерний комментарий + смена статуса), шлёт уведомление в Telegram.

> 📌 **Атрибуция:** идея и исходная архитектура взяты из публичных репозиториев `github.com/MrGAN12009/worker_ai` (ассистент-обработчик) и `github.com/MrGAN12009/app_test_2803` (тестовый сайт отзывов). Текущая версия переработана в единый самодостаточный двухсервисный проект.

**Ключевые параметры:**

| Параметр | Значение |
|----------|----------|
| Сайт | FastAPI + SQLAlchemy 2.x async + asyncpg + Jinja2 |
| БД | PostgreSQL 16 |
| Обработчик | Python 3.12, asyncio, httpx |
| LLM | OpenAI / GigaChat (Chat Completions) + словарный fallback |
| Классификатор тона | Словарь маркеров (без LLM) |
| Уведомления | Telegram Bot API (sendMessage) |
| Состояние | Локальный JSON (`state.json`) |
| Контейнеризация | Docker Compose (единый: db + site + worker) |
| Observability | stdout-логирование + execution-tracing + аудит |

---

## 📊 2. Current Status

**Стадия:** ✅ Портфельный актив (публичное демо). Доработка реализована (site + worker + единый compose + `/admin` runtime-config + демо-RBAC + мультипровайдерность + промпт-в-файле + три контура observability), Deployment Validation пройдена в чистом окружении (17/17 PASS), публичный репозиторий опубликован (github.com/AlexLvGulyaev/review-auto-responder), живое демо развёрнуто за обратным прокси (Traefik, TLS) по адресу https://review-auto-responder.alex-n8n.site (ответы генерируются через GigaChat).

### ✅ Завершённые задачи

- [x] Анализ legacy-репозиториев-референсов (`worker_ai`, `app_test_2803`, публичные репозитории github.com/MrGAN12009) как отправной точки.
- [x] Анализ as-built архитектуры: путь данных, файлы по этапам, взаимодействие `client.py`/`processor.py`/`worker.py`, роль `state.py`.
- [x] Зафиксированы исходные требования и рамки доработки.
- [x] **Observability — три контура:** централизованное stdout-логирование (`LOG_LEVEL`), execution-tracing обработки отзыва (`/admin/executions`, LLM-метрики в трассах), аудит admin/security-событий (`/admin/audit`). Верифицировано на живом публичном демо.

### 🔴 Высокий приоритет

- [x] **Утвердить направление доработки** — выбран полный объём доработки (портфолио-стиль).
- [x] **IMPLEMENTATION_PLAN** — `docs/IMPLEMENTATION_PLAN.md` готов; утверждён web-`/admin` runtime-config.
- [x] **Зафиксировать архитектуру как публичный артефакт** — схема пути данных (sequence/flow) в `docs/ARCHITECTURE.md`.

### 🟡 Средний приоритет

- [x] **Мультипровайдерность** — legacy захардкожен на OpenAI `responses.create`; реализован единый адаптер Chat Completions (OpenAI/GigaChat).
- [x] **Промпт в файле** — legacy-промпт захардкоден в `processor.py`; вынесен в `system_prompt.md` на shared volume (файл-SOT, mtime-кеш).
- [x] **Единый docker-compose** — единый compose (site + db + worker) с общим `WORKER_API_TOKEN`.
- [x] **`/health` эндпоинты** — добавлены на сайте и у обработчика (heartbeat) для Deployment Validation.

### 🟢 Низкий приоритет

- [x] **Server-side фильтр `?status=new`** — реализован серверный фильтр вместо клиентского по полному списку.
- [x] **Auth-симметрия** — `POST /api/reviews` и чтение открыты (legacy-модель доступа); токен-guard на `PATCH` (воркер); демо-RBAC на `/admin`. RBAC на публичную запись отложен в v1.0 (см. SECURITY_NOTES).
- [x] **Мёртвое поле `response`** — колонка `Review.response` зарезервирована; ответ публикуется дочерним комментарием (threaded-структура).

---

## 🛒 3. Market Validation

- Проект создан как портфельный кейс — демонстрация паттерна «парсер + автономная AI-обработка 24/7».
- Паттерн универсален: отзывы интернет-магазинов, отклики на фриланс-заказы (скрипт собирает → нейросеть проверяет соответствие навыкам → отклик за 10–15 с), любая задача «сбор данных + AI-реакция».
- Реалистичная область — НЕ парсинг Ozon/Wildberries (защита от ботов), а собственные сайты и официальные API маркетплейсов (API продавца).

---

## 💰 4. Commercial Assessment

**Потенциал:**

- Готовый шаблон «опросчик + классификатор + AI-ответ + уведомление» — переиспользуемая заготовка для клиентских автоматизаций.
- Дешёвая классификация (словарь маркеров) экономит токены: тон определяется без LLM, нейросеть — только для генерации ответа.
- Двухсервисная архитектура (сайт — активный участник, хранит статус) — масштабируема и наблюдаема.

**Риски:**

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|--------|------------|
| Захардкожен один провайдер (legacy) | — | — | ✅ Митигировано: мультипровайдерность (единый адаптер Chat Completions) |
| Промпт в коде — сложно варьировать (legacy) | — | — | ✅ Митигировано: `system_prompt.md` (файл-SOT) + правка через `/admin` |
| Два отдельных compose (legacy) — сложно воспроизвести | — | — | ✅ Митигировано: единый compose + DEPLOYMENT_GUIDE |
| Нет `/health` (legacy) — Deployment Validation затруднена | — | — | ✅ Митигировано: health-эндпоинты добавлены |
| Auth-асимметрия — открытые POST/чтение | Средняя | Среднее | Документировано; RBAC на публичную запись отложен в v1.0 |
| Качество ответа зависит от промпта/модели | Средняя | Среднее | Версионирование промптов, fallback, execution-tracing метрик LLM |

---

## 🔧 5. Key Technology Areas

**Компетенции:**

| Область | Компетенция | Статус |
|---------|-------------|--------|
| FastAPI + PostgreSQL | SQLAlchemy 2.x async, asyncpg, самоссылка parent_id | ✅ |
| Async-поллер | asyncio + httpx, интервал опроса, ожидание сайта | ✅ |
| Классификация тона | Словарь маркеров (без LLM) | ✅ |
| LLM-генерация ответа | Chat Completions: OpenAI/GigaChat + fallback | ✅ Мультипровайдерность |
| Идемпотентность | Локальный `state.json` (notified/processed) + статус на сайте | ✅ |
| Telegram-уведомления | Bot API sendMessage | ✅ |
| Защита от self-reply | Проверка `is_ai_authored` по имени + mark-processed | ✅ |
| Контейнеризация | Docker Compose (единый) | ✅ |
| Runtime-config | `/admin` → `config.json` (shared volume), hot-reload по mtime | ✅ |
| Observability | stdout-логирование + execution-tracing + аудит | ✅ |

---

## ✅ 6. Decision

**Принято:** продолжить как публичный портфолио-кейс — взять legacy-репозитории как референс, доработать до самодостаточного публичного репозитория с инженерной документацией и Deployment Validation.

**Реализованные решения:**

- База — legacy-архитектура (сайт + обработчик), доработка по направлениям §2.
- Мультипровайдерность: OpenAI / GigaChat (OAuth-адаптер) — единый адаптер Chat Completions. Смена провайдера через web-`/admin` в runtime, без рестарта (карточки провайдеров, radio «сделать активным»).
- Web-`/admin` на сайте (домстиль AIP Dark, единый хидер «Admin Console» + зелёный «Zerocoder», sidebar с role-бейджем, 4 консоли): `active_provider`/`fallback_provider`, per-провайдер `model`/`base_url`/`temperature`/`max_tokens`/`enabled` → `config.json` в shared volume; обработчик hot-reload'ит по mtime. Секреты остаются в `.env`. Кнопка «Проверить» — real-тест через внутренний test-API воркера (ключи только на воркере). Описательные тексты — тултипы.
- Промпт вынесен из `processor.py` в `system_prompt.md` на shared volume (файл-SOT); правка через `/admin` перезаписывает файл.
- Единый `docker-compose.yml` (site + db + worker) с общим `WORKER_API_TOKEN` + `/health` — для воспроизводимого Deployment Validation.
- Архитектура пути данных зафиксирована в `docs/ARCHITECTURE.md` (sequence-схема).
- Три контура observability: stdout-логирование (`LOG_LEVEL`), execution-tracing (`/admin/executions`), аудит (`/admin/audit`).
- Публичный репозиторий + живое демо за обратным прокси.

---

## 🚀 7. Next Steps

### Завершённые этапы

1. ~~Утвердить объём доработки~~ — выбран полный объём.
2. ~~`docs/IMPLEMENTATION_PLAN.md`~~ — технический план готов.
3. ~~Реализовать доработанную версию~~ — сайт + обработчик.
4. ~~Единый `docker-compose.yml` + `DEPLOYMENT_GUIDE.md` + `/health`~~.
5. ~~`docs/ARCHITECTURE.md`~~ — архитектура пути данных зафиксирована.
6. ~~Deployment Validation в чистом окружении~~ — 17/17 PASS.
7. ~~Публичный репозиторий + живое демо~~ — github.com/AlexLvGulyaev/review-auto-responder, https://review-auto-responder.alex-n8n.site.
8. ~~Observability~~ — три контура реализованы и верифицированы.

### Возможное развитие (за границей v1.0)

- RBAC / токенизация с квотой на публичную форму `POST /api/reviews` (см. SECURITY_NOTES §3–4).
- CA-bundle для GigaChat на production вместо `ssl.CERT_NONE`.
- Схлопывание execution-tracing в один POST (create-with-steps) при росте объёмов.

---

## 🔗 8. Dependencies

| Зависимость | Описание | Влияние |
|-------------|----------|---------|
| Тестовый сайт отзывов | Цель опроса; источник новых отзывов, приёмник ответов | Блокирует весь поток |
| LLM-провайдер | Генерация ответа (OpenAI/GigaChat) | Fallback на словарные шаблоны при сбое/отсутствии ключа |
| Telegram Bot API | Уведомления оператора | Опционально; без токена — пропуск |
| PostgreSQL | Хранилище отзывов сайта + таблицы observability | Блокирует сайт |
| VPS / Docker Host | Развёртывание 24/7 | Блокирует публичный деплой |

---

## 📜 9. Status History

| Дата | Статус | Примечание |
|------|--------|------------|
| 2026-08-13 | Старт кейса | Legacy-репозитории-референсы клонированы (публичные репозитории github.com/MrGAN12009); зафиксированы исходные требования |
| 2026-08-13 | Анализ архитектуры | Восстановлена as-built архитектура: путь данных, файлы по этапам, взаимодействие client/processor/worker, роль state-файла; выявлены дефициты и точки доработки |
| 2026-08-13 | PROJECT_STATE | Зафиксировано состояние и предложено направление доработки (портфолио-стиль) |
| 2026-08-13 | IMPLEMENTATION_PLAN | Утверждён web-`/admin` runtime-config (портфолио-стиль); технический план готов к разработке |
| 2026-08-13 | Разработка | Реализованы review-site (FastAPI + PostgreSQL, `/admin` демо-RBAC) и review-worker (мультипровайдер, runtime-config, heartbeat); единый `docker-compose.yml`; инженерная документация. Исправлены: `python-multipart`, баг серверного фильтра `?status` (alias) |
| 2026-08-13 | Deployment Validation | Чистое окружение (teardown → пересборка по DEPLOYMENT_GUIDE): 17/17 PASS — 3 отзыва разной тональности, switch OpenAI↔GigaChat без рестарта (реальный ответ GigaChat), демо-RBAC 403/401, fallback, healthcheck-и |
| 2026-08-13 | Портфельный актив | Публичный репозиторий опубликован (github.com/AlexLvGulyaev/review-auto-responder); public-boundary соблюдён |
| 2026-08-13 | Публичное демо | Живое демо развёрнуто за Traefik (TLS) на https://review-auto-responder.alex-n8n.site: router+service в dynamic.yml, review-site в сети прокси (override, gitignored), GigaChat верифицирован реальным ответом на публичном эндпоинте; DEPLOYMENT_GUIDE §8 дополнен production-разделом |
| 2026-08-13 | Observability | Три контура: stdout-логирование (`LOG_LEVEL`, dictConfig, приглушённые httpx/openai), execution-tracing (`execution_sessions`+`execution_steps`, воркер пишет через API сайта, `/admin/executions` с LLM-метриками provider/model/latency_ms/tokens/fallback_reason), аудит (`audit_logs`, `/admin/audit`, события login/config/rbac/worker_denied). Верифицировано на живом демо (GigaChat: tokens=192, latency_ms=663); коммит `8e61c5e` в origin/main; public-boundary кода очищен |
| 2026-08-13 | AIP Dark + file-SOT | Редизайн админки в домстиле AIP Dark (sidebar, 4 консоли); промпт — файл-SOT на shared volume (`system_prompt.md`, bootstrap из `prompts/v1/system.md`); консоль состояния системы `/admin/status` + `status.json` воркера в shared volume (liveness + bool-флаги провайдеров, без секретов) |
| 2026-08-13 | Конфиг-консоль v1.3 | Двухколоночный лэйаут конфиг-консоли (карточки провайдеров OpenAI/GigaChat слева, промпт справа); ряд состояния системы — 5 плиток (PostgreSQL/Воркер/LLM/Telegram/API); per-provider модели (`gigachat_model`); Yandex-провайдер убран из кода и docs |
| 2026-08-13 | Конфиг-консоль v1.4 | Паритет с эталонной Admin Console: единый статический хидер «Admin Console» + зелёный «Zerocoder»; role-бейдж в сайдбаре; per-console page-header. Две панели («Настройки LLM и провайдера» | «Системный промпт») side-by-side; карточки провайдеров слева направо со всеми параметрами (Base URL/Model/Temperature/Max tokens/Включён/Проверить); active/fallback LLM-chain; тултипы вместо inline-текстов; шрифты выровнены под эталон. Внутренний test-API воркера (`worker/api.py`, stdlib asyncio, порт 8001 не публикуется) + site-proxy `/admin/test-provider` — real-тест «Проверить» без передачи ключей на сайт |

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта.
- [📋 `docs/IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — план реализации.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура и путь данных.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты HTTP API.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры LLM-провайдеров.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность и демо-RBAC.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание с нуля.
- [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) — отчёт воспроизводимости.
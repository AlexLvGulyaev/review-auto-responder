# 📂 PROJECT_STRUCTURE.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата:** 2026-08-14
**Статус:** Engineering Layer — карта репозитория для инженеров и интеграторов.

Полное файловое дерево публичного репозитория с комментарием на каждый файл.
Краткая сводка для README — в [🏠 `README.md` §8](../README.md#-8-структура-проекта).

---

## 📁 Дерево репозитория

```text
review-auto-responder/
├── README.md                            # Точка входа в проект
├── .env.example                         # Шаблон переменных окружения (заполнить → .env)
├── .gitignore
├── docker-compose.yml                   # Единая среда: db + review-site + review-worker
├── docs/                                # Публичная документация
│   ├── BUSINESS_VALUE.md                # Бизнес-ценность, эффект, выгода
│   ├── SYSTEM_DEMO.md                   # Скриншот-тур и демо-сценарии
│   ├── E2E_SCENARIOS.md                 # Сквозные сценарии (сайт + /admin + Telegram)
│   ├── USER_GUIDE.md                    # Руководство посетителя сайта отзывов
│   ├── OPERATOR_GUIDE.md                # Руководство оператора /admin
│   ├── ARCHITECTURE.md                  # Архитектура, C4-схемы, модель данных, потоки
│   ├── SPEC.md                          # Продуктовая спецификация (замороженный baseline)
│   ├── IMPLEMENTATION_PLAN.md           # Технический план и критерии готовности
│   ├── API_CONTRACT.md                  # Контракты HTTP API сайта и воркера
│   ├── PROMPT_ARCHITECTURE.md           # Архитектура промпта (файл-SOT, lifecycle, аудит)
│   ├── EXTERNAL_PROVIDERS.md            # Параметры LLM-провайдеров (OpenAI/GigaChat)
│   ├── SECURITY_NOTES.md                # Безопасность, демо-RBAC, демо-лимиттер
│   ├── TESTING.md                       # Стратегия тестирования (4 уровня проверки)
│   ├── DEPLOYMENT_GUIDE.md              # Развёртывание с нуля (Source of Truth)
│   ├── DEPLOYMENT_VALIDATION_REPORT.md  # Отчёт воспроизводимости (18/18 PASS)
│   ├── PROJECT_STATE.md                 # Паспорт состояния проекта и roadmap
│   └── screenshots/                     # Иллюстрации системы
│       ├── MEDIA_INDEX.md               # Каталог медиаматериалов
│       └── RAR_*.png                    # 15 скриншотов (сайт, /admin, Telegram)
├── site/                                # Сайт отзывов (FastAPI + PostgreSQL)
│   ├── Dockerfile                       # python:3.12-slim, uvicorn
│   ├── requirements.txt                 # fastapi, sqlalchemy, asyncpg, jinja2
│   └── app/
│       ├── main.py                      # FastAPI app, lifespan (idempotent init схемы), router
│       ├── config.py                    # Pydantic-settings: БД, токены, runtime-config, LOG_LEVEL
│       ├── schemas.py                   # Pydantic-схемы (Review, execution, audit, demo)
│       ├── api/                         # Роуты
│       │   ├── routes.py                # GET /, GET /api/reviews?status=, POST/PATCH /api/reviews, /health
│       │   ├── admin.py                 # /admin: демо-RBAC, login/logout, writer config.json
│       │   ├── admin_status.py          # GET /admin/status — сводка здоровья (БД, воркер, провайдеры)
│       │   ├── executions.py            # POST/PATCH /api/executions — трейсы воркера под X-Worker-Token
│       │   ├── admin_executions.py      # GET /admin/executions — read-only просмотр трейсов
│       │   ├── audit.py                 # GET /admin/audit — read-only журнал аудита
│       │   ├── demo.py                  # POST /api/demo/start, GET /api/demo/status (v1.5)
│       │   └── worker_auth.py           # require_worker_token → 401 + audit при плохом токене
│       ├── models/                      # SQLAlchemy-модели
│       │   ├── review.py                # Review (самоссылка parent_id, status, tone)
│       │   ├── execution.py             # ExecutionSession + ExecutionStep (execution-tracing)
│       │   ├── audit.py                 # AuditLog (журнал admin/security-событий)
│       │   └── demo_session.py          # DemoSession — токенизированная демо-квота (v1.5)
│       ├── services/
│       │   ├── audit.py                 # AuditService.log_audit + определение client_ip
│       │   └── demo_limiter.py          # DemoLimiterService — 3 уровня квоты (v1.5)
│       ├── core/
│       │   └── logging.py               # configure_logging через dictConfig (контур 1)
│       ├── db/
│       │   ├── base.py                  # DeclarativeBase
│       │   └── session.py               # async engine, session factory, get_db_session
│       └── templates/                   # Jinja2
│           ├── index.html               # Сайт отзывов (опрос 5с, дерево тредов)
│           ├── admin_base.html          # Базовый шаблон /admin (AIP Dark, общий хидер/sidebar)
│           ├── admin.html               # Конфиг-консоль + observability + аудит
│           ├── admin_login.html         # Вход (полный токен / одно-кликовой демо-вход)
│           ├── executions.html          # Список execution-трейсов
│           ├── execution_detail.html    # Детали трассы (шаги, LLM-метрики)
│           ├── audit.html               # Журнал аудита
│           └── audit_detail.html        # Детали записи аудита
└── worker/                              # Автономный обработчик (asyncio)
    ├── Dockerfile                       # python:3.12-slim, healthcheck по heartbeat
    ├── requirements.txt                 # httpx, openai, pydantic, pydantic-settings
    ├── worker.py                        # Основной цикл, execution-сессии, heartbeat
    ├── processor.py                     # detect_tone + generate_response + fallback
    ├── client.py                        # httpx-клиент к API сайта (reviews + executions)
    ├── runtime_config.py                # mtime-кеш config.json (hot-reload без рестарта)
    ├── prompt_loader.py                 # Чтение system_prompt.md из shared volume (файл-SOT)
    ├── state.py                         # state.json: notified/processed (defensive guard)
    ├── api.py                           # Внутренний test-API (POST /provider-test, не публикуется)
    ├── healthcheck.py                   # Проверка heartbeat для Docker healthcheck
    ├── telegram_bot.py                  # Уведомление оператору о новом отзыве (опционально)
    ├── models.py                        # RemoteReview, payload'ы, ReviewStatus, ReviewTone
    ├── config.py                        # Pydantic-settings: секреты + пути, LOG_LEVEL
    ├── logging_config.py                # configure_logging + приглушённые httpx/openai
    ├── prompts/v1/system.md             # Системный промпт (bootstrap-default для shared volume)
    └── providers/                       # LLM-провайдеры (единая абстракция Chat Completions)
        ├── base.py                      # ResponseProvider ABC: generate / test_connection / last_usage
        ├── factory.py                   # build_active/fallback по config.json + *_enabled
        ├── openai_provider.py           # OpenAI Chat Completions (base_url/temperature/max_tokens из runtime)
        ├── gigachat_provider.py         # GigaChat — async-обёртка над адаптером (asyncio.to_thread)
        └── gigachat_adapter.py          # GigaChat — прямой HTTP, OAuth-обмен per-request, сертификат Минцифры
```

> ℹ️ `__init__.py` опущены для краткости. Секреты (`OPENAI_API_KEY`,
> `GIGACHAT_AUTH_KEY`, `ADMIN_TOKEN`, `WORKER_API_TOKEN`) — только в `.env`
> (в `.gitignore`), в репозитории их нет. `config.json` и `system_prompt.md`
> живут в Docker volume `runtime-config` (не в дереве репозитория) —
> см. [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура, C4-схемы, модель данных.
- [📋 `docs/IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — технический план и состав компонентов.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты HTTP API.
# 🏠 Review Auto Responder

Автономный AI-ассистент, который 24/7 собирает новые отзывы с сайта, определяет их тональность, генерирует уместный ответ нейросетью и уведомляет оператора в Telegram. Демонстрация универсального паттерна **«парсер + автономная AI-обработка»** с переключаемым LLM-провайдером.

> 🌐 **Живое демо:** <https://review-auto-responder.alex-n8n.site> — публичный сайт отзывов; ответы генерируются нейросетью (GigaChat). Операторская панель: <https://review-auto-responder.alex-n8n.site/admin>.

> 📌 **Атрибуция:** идея и исходная архитектура взяты из публичных репозиториев [`MrGAN12009/worker_ai`](https://github.com/MrGAN12009/worker_ai) (ассистент-обработчик) и [`MrGAN12009/app_test_2803`](https://github.com/MrGAN12009/app_test_2803) (тестовый сайт отзывов). Текущая версия переработана в единый двухсервисный проект с мультипровайдерностью (OpenAI/GigaChat), операторской панелью `/admin` (смена провайдера/модели/промпта в runtime без рестарта), промптом в файле, демо-RBAC, `/health`, server-side фильтром и публичной документацией с Deployment Validation.

---

## 🎬 Демо-тур

Короткий визуальный обзор системы. Полный скриншот-тур — в [🎬 `docs/SYSTEM_DEMO.md`](docs/SYSTEM_DEMO.md).

**Публичный сайт отзывов** — посетитель оставляет отзыв, воркер автономно отвечает от `AI Support` в той же ветке:

![Сайт отзывов: форма слева, тред с отзывами и ответами AI Support справа](docs/screenshots/RAR_site_thread.png)

**Операторская панель `/admin`** — вход (полный токен или одно-кликовой демо-вход) и конфиг-консоль runtime-переключения провайдера/модели/промпта:

![Вход в /admin: два пути — токен и демо-кнопка](docs/screenshots/RAR_admin_login.png)

![Конфиг-консоль /admin: карточки провайдеров, промпт, состояние системы](docs/screenshots/RAR_admin_config.png)

**Telegram-уведомление оператору** — каждый новый отзыв с тональностью:

![Telegram-уведомление оператору о новом отзыве](docs/screenshots/RAR_tg_review_notification.png)

---

## 🎯 1. Что это

Команда поддержки получает отзывы через публичный сайт. Вместо ручного мониторинга страницы:

- **Сайт отзывов** принимает отзывы клиентов и хранит их в виде threaded-комментариев.
- **Обработчик** (воркер) автономно опрашивает сайт, определяет тон (позитивный / негативный / нейтральный), генерирует ответ от лица компании и публикует его как дочерний комментарий.
- **Оператор** мгновенно узнаёт о новых отзывах через Telegram — и может подключиться лично к негативу, где ИИ не решит вопрос.

Система не падает без LLM-ключа: при сбое или отсутствии провайдера отвечает словарными fallback-шаблонами по тону.

---

## 💡 2. Ключевые возможности

| Возможность | Описание |
|-------------|----------|
| 🤖 **Мультипровайдерность** | OpenAI / GigaChat (Сбер) — через единую абстракцию Chat Completions; per-провайдер temperature/max_tokens; active/fallback LLM-цепочка; карточки провайдеров в `/admin` |
| 🎛️ **Смена провайдера без рестарта** | Операторская панель `/admin`: активный/fallback провайдер, модель, base_url, temperature, max_tokens, промпт — применяются на следующем цикле опроса |
| ✅ **«Проверить»** | Real-тест доступности LLM-провайдера (1-токенный вызов) через внутренний test-API воркера — ключи остаются на воркере, сайт их не получает |
| 📝 **Промпт — файл-SOT** | `system_prompt.md` на shared volume — единственный SOT промпта; `/admin` перезаписывает его (bootstrap из вшитого `prompts/v1/system.md`) |
| 🔐 **Демо-RBAC админки** | Два токена: полный (`ADMIN_TOKEN`) и read-only демо (`ADMIN_DEMO_TOKEN`) — backend-guard на мутации |
| 🖥️ **AIP Dark админка** | Единый хидер «Admin Console» + «Zerocoder», sidebar с role-бейджем; Конфиг-консоль (провайдеры + промпт + состояние системы), Обсервабилити, Аудит |
| 📈 **Консоль состояния системы** | `/admin/status`: живая проба БД, метрики, liveness воркера, статус провайдеров (воркер пишет `status.json` в shared volume) |
| 🏷️ **Тональность без LLM** | Словарный классификатор — экономия токенов и предсказуемость |
| 🔁 **Защита от self-reply** | Воркер не отвечает на собственные ответы — бесконечный цикл исключён |
| 📣 **Telegram-уведомления** | Оператор получает каждый новый отзыв с тоном и текстом |
| 🛡️ **Fallback** | active LLM → fallback LLM → словарные шаблоны — система отвечает даже без ключей |
| 📊 **Observability** | Три контура: stdout-логи (`LOG_LEVEL`), execution-трейсы обработки (`/admin/executions`), журнал аудита (`/admin/audit`) |
| 🚀 **Единый compose** | `docker compose up --build -d` поднимает БД + сайт + воркер |

---

## 🛠️ 3. Стек

- **Сайт:** FastAPI, SQLAlchemy 2 (async), asyncpg, PostgreSQL 16, Jinja2.
- **Воркер:** asyncio, httpx, openai SDK, urllib (GigaChat OAuth-адаптер).
- **Инфраструктура:** Docker, Docker Compose, healthcheck-и на каждом сервисе.

---

## 🚀 4. Быстрый старт

```bash
git clone https://github.com/AlexLvGulyaev/review-auto-responder.git
cd review-auto-responder
cp .env.example .env      # заполнить секреты (минимум — токены)
docker compose up -d --build
```

Сайт: `http://localhost:8000` · Health: `http://localhost:8000/health` · Админка: `http://localhost:8000/admin`

> 📌 Минимум для запуска: переменные БД + `WORKER_API_TOKEN` + `ADMIN_TOKEN` + `ADMIN_DEMO_TOKEN`. Без LLM-ключа воркер уходит в fallback — система отвечает словарными шаблонами.

Полная инструкция развёртывания, smoke-тест (3 отзыва разной тональности), проверка демо-RBAC и адаптация для production — в [🚀 `docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md).

---

## 🧪 5. Проверка работы

1. Оставьте три отзыва на сайте: позитивный, негативный, нейтральный.
2. В течение нескольких секунд воркер определит тон, сгенерирует ответ от `AI Support` и переведёт отзывы в `processed`.
3. (Опционально) При настроенном Telegram — придёт уведомление оператору.

Подробно — [🚀 DEPLOYMENT_GUIDE.md §4](docs/DEPLOYMENT_GUIDE.md).

---

## 📊 6. Observability — три контура

| Контур | Носитель | Назначение | Просмотр |
|--------|----------|-----------|----------|
| **stdout-логирование** | `docker compose logs` | Этапы обработки, сбои провайдера; уровень через `LOG_LEVEL` | логи сервисов |
| **Состояние системы** | БД-пробы + `status.json` (shared volume) | overall/БД, метрики, liveness воркера, статус провайдеров, последние ошибки | `/admin/status` + блок в `/admin` |
| **Execution tracing** | БД (`execution_sessions` + `execution_steps`) | Трасса пайплайна каждого отзыва: статус, провайдер/модель, длительность, LLM-метрики (latency/tokens/fallback_reason) | `/admin/executions` |
| **Audit** | БД (`audit_logs`) | Журнал admin/security-событий: входы в `/admin`, смена конфига, RBAC-отказы, отказы `X-Worker-Token` | `/admin/audit` |

Панели `/admin/executions`, `/admin/audit` и `/admin/status` — read-only,
доступны и admin-, и demo-токеном. Подробно — [🏗️ ARCHITECTURE.md §7](docs/ARCHITECTURE.md),
[🛡️ SECURITY_NOTES.md §6–7](docs/SECURITY_NOTES.md),
[🔌 API_CONTRACT.md §2.4, §3–4](docs/API_CONTRACT.md).

---

## 📚 7. Документация

**Пользование и демо:**
- [📖 `docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — как пользоваться сайтом отзывов.
- [🎬 `docs/SYSTEM_DEMO.md`](docs/SYSTEM_DEMO.md) — скриншот-тур по системе.
- [🎬 `docs/E2E_SCENARIOS.md`](docs/E2E_SCENARIOS.md) — сквозные демо-сценарии (сайт + `/admin` + Telegram).
- [🎛️ `docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md) — руководство оператора `/admin` (runtime-config, промпт, observability).
- [💼 `docs/BUSINESS_VALUE.md`](docs/BUSINESS_VALUE.md) — ценность, целевая аудитория, паттерн «сбор + AI-реакция 24/7».

**Техническая:**
- [🏗️ `docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура и путь данных.
- [📋 `docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — технический план.
- [🔌 `docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — контракты HTTP API.
- [📝 `docs/PROMPT_ARCHITECTURE.md`](docs/PROMPT_ARCHITECTURE.md) — архитектура промпта (файл-SOT, lifecycle, аудит).
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](docs/EXTERNAL_PROVIDERS.md) — параметры LLM-провайдеров.
- [🛡️ `docs/SECURITY_NOTES.md`](docs/SECURITY_NOTES.md) — безопасность, демо-RBAC и демо-лимиттер.

**Развёртывание и проверка:**
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) — развёртывание с нуля (SOT воспроизводимости).
- [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](docs/DEPLOYMENT_VALIDATION_REPORT.md) — отчёт воспроизводимости в чистом окружении.
- [🧪 `docs/TESTING.md`](docs/TESTING.md) — стратегия тестирования (4 уровня проверки).
- [📊 `docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — паспорт состояния проекта.
- [📋 `docs/SPEC.md`](docs/SPEC.md) — продуктовая спецификация (замороженный baseline).

---

## 📂 8. Структура проекта

```
.
├── docker-compose.yml          # Единая среда: db + site + worker
├── .env.example                # Переменные окружения (заполнить → .env)
├── site/                       # Сайт отзывов (FastAPI + PostgreSQL)
│   └── app/
│       ├── api/                # routes, admin, executions, audit, worker_auth
│       ├── models/             # Review, ExecutionSession/Step, AuditLog
│       ├── services/           # AuditService (журнал аудита)
│       ├── core/               # configure_logging (контур 1)
│       ├── templates/          # index, admin, admin_login, executions, audit
│       └── ...
├── worker/                     # Автономный обработчик
│   ├── worker.py               # Основной цикл + execution-сессии + heartbeat
│   ├── processor.py            # detect_tone + generate_response + fallback
│   ├── client.py               # httpx-клиент к API сайта (rev. + executions)
│   ├── providers/              # openai / gigachat / factory
│   ├── prompts/v1/system.md    # Системный промпт (SOT текста)
│   └── ...
└── docs/                       # Документация
```

---

## 📝 9. История

| Дата | Версия | Изменение |
|------|--------|-----------|
| 2026-08-13 | 1.0 | Доработка legacy: мультипровайдерность, `/admin` runtime-config, промпт-в-файле, единый compose, демо-RBAC, `/health`, Deployment Validation |
| 2026-08-13 | 1.1 | Observability: три контура — stdout-логирование (`LOG_LEVEL`), execution-tracing (`/admin/executions`), аудит (`/admin/audit`); LLM-метрики в трассах |
| 2026-08-13 | 1.2 | AIP Dark-редизайн админки (sidebar, 4 консоли); промпт — файл-SOT на shared volume (`system_prompt.md`, bootstrap из `prompts/v1/system.md`); консоль состояния системы `/admin/status` (БД-пробы, метрики, liveness воркера через `status.json` в shared volume, статус провайдеров) |
| 2026-08-13 | 1.3 | Конфиг-консоль: двухколоночный лэйаут (карточки провайдеров OpenAI/GigaChat слева, промпт справа); ряд состояния системы — 5 плиток (PostgreSQL/Воркер/LLM/Telegram/API); per-provider модели (`gigachat_model`); Yandex-провайдер убран из кода и docs |
| 2026-08-13 | 1.4 | Паритет конфиг-консоли с эталонной Admin Console: единый хидер «Admin Console» + «Zerocoder», role-бейдж в сайдбаре, per-console page-header; две панели side-by-side («Настройки LLM и провайдера» \| «Системный промпт»); карточки провайдеров слева направо со всеми параметрами (Base URL/Model/Temperature/Max tokens/Включён/Проверить); active/fallback LLM-цепочка; тултипы вместо inline-текстов; выровнены шрифты. «Проверить» — real-тест через внутренний test-API воркера (`worker/api.py`, stdlib asyncio, порт не публикуется) + site-proxy `/admin/test-provider` (ключи только на воркере) |
| 2026-08-14 | 1.5 | Демо-стандарт входа и сессионные лимиты: одно-кликовой демо-вход в `/admin` (сервер ставит cookie, токен не попадает в браузер) + токенизированный демо-лимиттер публичной формы `POST /api/reviews` (квота 5/сессию, 3 уровня — sessions/IP/час, rate-limit, квота; воркер exempt по `X-Worker-Token`) |
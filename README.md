# 🏠 Review Auto Responder

Автономный AI-ассистент, который 24/7 собирает новые отзывы с сайта, определяет их тональность, генерирует уместный ответ нейросетью и уведомляет оператора в Telegram. Демонстрация универсального паттерна **«парсер + автономная AI-обработка»** с переключаемым LLM-провайдером.

> 🌐 **Живое демо:** <https://review-auto-responder.alex-n8n.site> — публичный сайт отзывов; ответы генерируются нейросетью (GigaChat). Операторская панель: <https://review-auto-responder.alex-n8n.site/admin>.

> 📌 **Атрибуция:** идея и исходная архитектура взяты из публичных репозиториев [`MrGAN12009/worker_ai`](https://github.com/MrGAN12009/worker_ai) (ассистент-обработчик) и [`MrGAN12009/app_test_2803`](https://github.com/MrGAN12009/app_test_2803) (тестовый сайт отзывов). Текущая версия переработана в единый двухсервисный проект с мультипровайдерностью (OpenAI/GigaChat), операторской панелью `/admin` (смена провайдера/модели/промпта в runtime без рестарта), промптом в файле, демо-RBAC, `/health`, server-side фильтром и публичной документацией с Deployment Validation.

---

## 🌐 Публичные точки входа

| Точка | URL | Назначение |
|-------|-----|-----------|
| **Сайт отзывов** | `https://review-auto-responder.alex-n8n.site/` | Публичная форма: оставить отзыв, читать тред с ответами `AI Support` |
| **Операторская панель** | `…/admin` | runtime-config провайдеров/промпта, observability, аудит (вход — полный токен или демо-режим) |
| **Демо-вход в админку** | `…/admin/login/demo` | Одно-кликовой read-only просмотр без токена в браузере (сервер ставит cookie) |
| **Health** | `…/health` | `{"status":"ok"}` — Deployment Verification/Validation |
| **Telegram** | оператору | Уведомление о каждом новом отзыве с тональностью (опционально) |

> 📌 Локально после `docker compose up -d --build`: сайт — `http://localhost:8000/`,
> админка — `…/admin`, health — `…/health`. Посетителю регистрация не нужна — только
> текст отзыва.

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
| 📝 **Промпт — файл-SOT** | Промпт хранится в файле и редактируется в runtime через `/admin` (правка без деплоя) — детали в [📝 `PROMPT_ARCHITECTURE.md`](docs/PROMPT_ARCHITECTURE.md) |
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

## 📊 6. Observability

Три контура наблюдаемости: stdout-логи (`docker compose logs`, `LOG_LEVEL`),
execution-трейсы обработки каждого отзыва (`/admin/executions`) и журнал
admin/security-событий (`/admin/audit`). Сводное состояние — `/admin/status`
и блок «Состояние системы» в `/admin`. Все панели read-only, доступны и admin-,
и demo-токеном. Подробно — [🏗️ ARCHITECTURE.md §8](docs/ARCHITECTURE.md),
[🎛️ OPERATOR_GUIDE.md §7](docs/OPERATOR_GUIDE.md),
[🛡️ SECURITY_NOTES.md §6–7](docs/SECURITY_NOTES.md).

---

## 📚 7. Документация

### Для заказчиков и менеджеров

| Документ | Описание |
|----------|----------|
| [💼 `docs/BUSINESS_VALUE.md`](docs/BUSINESS_VALUE.md) | Бизнес-проблема, решение, эффект, выгода |
| [🎬 `docs/SYSTEM_DEMO.md`](docs/SYSTEM_DEMO.md) | Скриншоты, диалоги, бизнес-сценарии |
| [🎬 `docs/E2E_SCENARIOS.md`](docs/E2E_SCENARIOS.md) | Сквозные сценарии (сайт + `/admin` + Telegram) |

### Для пользователей и операторов

| Документ | Описание |
|----------|----------|
| [📖 `docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | Как пользоваться сайтом отзывов посетителю |
| [🎛️ `docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md) | Управление `/admin`: runtime-config, промпт, observability |

### Для инженеров и интеграторов

| Документ | Описание |
|----------|----------|
| [🏗️ `docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Архитектура, C4-схемы, модель данных, потоки данных |
| [📂 `docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) | Полное файловое дерево репозитория с комментариями |
| [📋 `docs/SPEC.md`](docs/SPEC.md) | Продуктовая спецификация (замороженный baseline) |
| [📋 `docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Технический план и критерии готовности |
| [🔌 `docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Контракты HTTP API сайта и воркера |
| [📝 `docs/PROMPT_ARCHITECTURE.md`](docs/PROMPT_ARCHITECTURE.md) | Архитектура промпта (файл-SOT, lifecycle, аудит) |
| [🤖 `docs/EXTERNAL_PROVIDERS.md`](docs/EXTERNAL_PROVIDERS.md) | Параметры LLM-провайдеров (OpenAI/GigaChat) |
| [🛡️ `docs/SECURITY_NOTES.md`](docs/SECURITY_NOTES.md) | Безопасность, демо-RBAC, демо-лимиттер |
| [🧪 `docs/TESTING.md`](docs/TESTING.md) | Стратегия тестирования (4 уровня проверки) |
| [🚀 `docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) | Развёртывание с нуля (Source of Truth) |
| [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](docs/DEPLOYMENT_VALIDATION_REPORT.md) | Отчёт воспроизводимости в чистом окружении |
| [📊 `docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) | Паспорт состояния проекта и roadmap |

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

Полное файловое дерево репозитория с комментарием на каждый файл — в
[📂 `docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md).

---

## ✅ 9. Статус проекта

✅ **Портфельный актив.** Реализован, прошёл Deployment Validation в чистом
окружении (18/18 PASS), опубликован как публичный репозиторий с живым демо.

Текущая версия — **v1.5**: демо-стандарт входа в админку (одно-кликовой server-side
demo-login) + токенизированный демо-лимиттер публичной формы (квота 5/сессию).

Полная история статусов и roadmap — в [📊 `docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md).
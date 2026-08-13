# 🏠 Review Auto Responder

Автономный AI-ассистент, который 24/7 собирает новые отзывы с сайта, определяет их тональность, генерирует уместный ответ нейросетью и уведомляет оператора в Telegram. Демонстрация универсального паттерна **«парсер + автономная AI-обработка»** с переключаемым LLM-провайдером.

> 🌐 **Живое демо:** <https://review-auto-responder.alex-n8n.site> — публичный сайт отзывов; ответы генерируются нейросетью (GigaChat). Операторская панель: <https://review-auto-responder.alex-n8n.site/admin>.

> 📌 **Атрибуция:** идея и исходная архитектура взяты из учебных репозиториев преподавателя [`MrGAN12009/worker_ai`](https://github.com/MrGAN12009/worker_ai) (ассистент-обработчик) и [`MrGAN12009/app_test_2803`](https://github.com/MrGAN12009/app_test_2803) (тестовый сайт отзывов). Текущая версия переработана в единый двухсервисный проект с мультипровайдерностью (OpenAI/GigaChat/YandexGPT), операторской панелью `/admin` (смена провайдера/модели/промпта в runtime без рестарта), промптом в файле, демо-RBAC, `/health`, server-side фильтром и публичной документацией с Deployment Validation.

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
| 🤖 **Мультипровайдерность** | OpenAI / GigaChat (Сбер) / YandexGPT / «Свой» — через единую абстракцию Chat Completions |
| 🎛️ **Смена провайдера без рестарта** | Операторская панель `/admin`: провайдер, модель, base_url, промпт — применяются на следующем цикле опроса |
| 📝 **Промпт в файле** | `prompts/v1/system.md` вместо хардкода; override через `/admin` |
| 🔐 **Демо-RBAC админки** | Два токена: полный (`ADMIN_TOKEN`) и read-only демо (`ADMIN_DEMO_TOKEN`) — стандартный демо-сценарий APL |
| 🏷️ **Тональность без LLM** | Словарный классификатор — экономия токенов и предсказуемость |
| 🔁 **Защита от self-reply** | Воркер не отвечает на собственные ответы — бесконечный цикл исключён |
| 📣 **Telegram-уведомления** | Оператор получает каждый новый отзыв с тоном и текстом |
| 🛡️ **Fallback** | Система отвечает даже без ключа/при сбое API |
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

## 📚 6. Документация

- [🏗️ `docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура и путь данных.
- [📋 `docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — технический план.
- [🔌 `docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — контракты HTTP API.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](docs/EXTERNAL_PROVIDERS.md) — параметры LLM-провайдеров.
- [🛡️ `docs/SECURITY_NOTES.md`](docs/SECURITY_NOTES.md) — безопасность и демо-RBAC.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) — развёртывание с нуля.
- [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](docs/DEPLOYMENT_VALIDATION_REPORT.md) — отчёт воспроизводимости.

---

## 📂 7. Структура проекта

```
.
├── docker-compose.yml          # Единая среда: db + site + worker
├── .env.example                # Переменные окружения (заполнить → .env)
├── site/                       # Сайт отзывов (FastAPI + PostgreSQL)
│   └── app/
│       ├── api/                # routes.py (отзывы) + admin.py (/admin, демо-RBAC)
│       ├── models/             # Review (самоссылка parent_id)
│       ├── templates/          # index, admin, admin_login
│       └── ...
├── worker/                     # Автономный обработчик
│   ├── worker.py               # Основной цикл + heartbeat
│   ├── processor.py            # detect_tone + generate_response + fallback
│   ├── providers/              # openai / gigachat / yandex / factory
│   ├── prompts/v1/system.md    # Системный промпт (SOT текста)
│   └── ...
└── docs/                       # Документация
```

---

## 📝 8. История

| Дата | Версия | Изменение |
|------|--------|-----------|
| 2026-08-13 | 1.0 | Доработка legacy: мультипровайдерность, `/admin` runtime-config, промпт-в-файле, единый compose, демо-RBAC, `/health`, Deployment Validation |
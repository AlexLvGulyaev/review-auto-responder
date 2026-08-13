# 🚀 DEPLOYMENT_GUIDE.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата:** 2026-08-13
**Статус:** Source of Truth воспроизводимости развёртывания.

> 📌 **SOT-дисциплина:** этот документ — единственный источник истины процесса развёртывания. Критерий качества — **успешное развёртывание по инструкции**, а не качество текста. Если после полного выполнения система не работоспособна — документ не актуален. Валидация — запуском в чистом окружении (см. [✅ DEPLOYMENT_VALIDATION_REPORT.md](DEPLOYMENT_VALIDATION_REPORT.md)).

---

## 🧰 1. Требования к окружению

| Требование | Версия | Проверка |
|------------|--------|----------|
| Docker Engine | 24+ | `docker --version` |
| Docker Compose | v2 (plugin) | `docker compose version` |
| ОС | Linux / macOS / Windows+WSL2 | — |
| RAM | ≥ 1 ГБ свободной | — |
| Порты | `8000` (сайт) свободен | `curl -I http://localhost:8000` (должен быть connection refused) |

> ℹ️ Порт сайта на хосте меняется через `APP_PORT` в `.env`.

---

## 🔧 2. Переменные окружения

### 🔧 2.1. Получение проекта

```bash
git clone https://github.com/AlexLvGulyaev/review-auto-responder.git
cd review-auto-responder
```

### 🔧 2.2. Файл `.env`

```bash
cp .env.example .env
```

Откройте `.env` и заполните **обязательные** переменные:

| Переменная | Обязательна? | Назначение |
|------------|--------------|-----------|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | да | Учётные данные БД (значения по умолчанию подходят для локального запуска) |
| `WORKER_API_TOKEN` | да | Общий токен site↔worker (придумайте свой) |
| `ADMIN_TOKEN` | да | Полный доступ к `/admin` |
| `ADMIN_DEMO_TOKEN` | да | Read-only доступ к `/admin` (демо) |
| `ADMIN_AUTH_ENABLED` | нет | `true` (по умолчанию); `false` — только локальные тесты |
| `OPENAI_API_KEY` | один из провайдеров | OpenAI/«Свой» |
| `GIGACHAT_AUTH_KEY` | один из провайдеров | GigaChat |
| `YANDEX_API_KEY` | один из провайдеров | YandexGPT |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_CHAT_ID` | нет | Уведомления оператору (без них — пропуск) |
| `APP_PORT` | нет | Порт сайта на хосте (по умолчанию `8000`) |
| `WORKER_POLL_INTERVAL` | нет | Интервал опроса, сек (по умолчанию `10`) |

> ⚠️ **Минимум для запуска:** БД-переменные + `WORKER_API_TOKEN` + `ADMIN_TOKEN` + `ADMIN_DEMO_TOKEN`. Без LLM-ключа воркер уйдёт в fallback (словарные шаблоны) — система отвечает, но без нейросети.

> ⚠️ **Не коммитьте `.env`.** Он в `.gitignore`. В репозитории — только `.env.example` с placeholder'ами.

---

## ▶️ 3. Запуск

### ▶️ 3.1. Сборка и старт

```bash
docker compose up -d --build
```

Поднимаются три сервиса: `db`, `review-site`, `review-worker`. Сайт ждёт готовности БД (`service_healthy`), воркер — готовности сайта.

### ▶️ 3.2. Проверка состояния сервисов

```bash
docker compose ps
```

Ожидаемый результат: `db`, `review-site`, `review-worker` — статус `Up (healthy)`.

> ℹ️ Воркер становится `healthy` после первой итерации цикла (heartbeat записан, `start_period: 40s`). До этого — `health: starting`.

### ▶️ 3.3. Health-эндпоинт сайта

```bash
curl -i http://localhost:8000/health
```

Ожидаемый результат: `200 OK`, тело `{"status":"ok"}`.

### ▶️ 3.4. Логи

```bash
docker compose logs -f review-worker
```

В логах воркера: `Worker started with poll interval=10 seconds...`, затем обработка отзывов.

---

## 🧪 4. Smoke-тест: три отзыва разной тональности

### 🧪 4.1. Оставить отзывы

```bash
# Позитивный
curl -s -X POST http://localhost:8000/api/reviews \
  -H "Content-Type: application/json" \
  -d '{"name":"Иван","text":"Отличный сервис, всё быстро и удобно, спасибо!"}' ; echo

# Негативный
curl -s -X POST http://localhost:8000/api/reviews \
  -H "Content-Type: application/json" \
  -d '{"name":"Пётр","text":"Ужасно, долго ждал, проблема не решена."}' ; echo

# Нейтральный
curl -s -X POST http://localhost:8000/api/reviews \
  -H "Content-Type: application/json" \
  -d '{"name":"Анна","text":"Получил заказ, вопросов нет."}' ; echo
```

### 🧪 4.2. Дождаться обработки

В течение `WORKER_POLL_INTERVAL` + время генерации ответа (несколько секунд).

### 🧪 4.3. Проверить результат

Откройте сайт: `http://localhost:8000/` — каждый отзыв получил дочерний ответ от `AI Support` и статус `processed`.

Или через API:

```bash
curl -s "http://localhost:8000/api/reviews" | python3 -m json.tool
```

Ожидаемый результат:
- 3 родительских отзыва со `status=processed`, `tone` = `positive`/`negative`/`neutral` соответственно;
- 3 дочерних комментария (`parent_id` указывает на родитель, `name=AI Support`) со `status=processed`.

### 🧪 4.4. Проверить self-reply guard

В списке `?status=new` нет ответов `AI Support` (они сразу переводятся в `processed`):

```bash
curl -s "http://localhost:8000/api/reviews?status=new" | python3 -m json.tool
```

Ожидаемый результат: `[]` (пустой список) после обработки.

---

## 🖥️ 5. Операторская панель `/admin`

### 🖥️ 5.1. Вход

Откройте `http://localhost:8000/admin` → форма ввода токена.

- **Полный доступ:** введите `ADMIN_TOKEN` → форма runtime-config с активной кнопкой сохранения.
- **Демо-доступ:** введите `ADMIN_DEMO_TOKEN` → форма с бейджем «👁 Демо-режим: только просмотр» и отключённой кнопкой сохранения.

### 🖥️ 5.2. Смена провайдера без рестарта

1. В `/admin` (токен `ADMIN_TOKEN`) выберите `provider=gigachat`, `openai_model=GigaChat-Max` → **Сохранить**.
2. Оставьте новый отзыв (см. §4.1).
3. В течение цикла опроса воркер подхватит новый `config.json` (mtime) и сгенерирует ответ через GigaChat — **без рестарта** контейнера.

> 📌 Проверьте в логах: `Runtime config reloaded: provider=gigachat model=GigaChat-Max`.

### 🖥️ 5.3. Проверка демо-RBAC

С demo-токеном попытка сохранить (`POST /admin`) через форму отключена. Прямой API-вызов подтверждает backend-guard:

```bash
# С demo-токеном — ожидается 403
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/admin \
  -H "Cookie: admin_token=<ADMIN_DEMO_TOKEN>" \
  -d "provider=openai&openai_model=gpt-4.1-mini"
```

Ожидаемый результат: `403`.

```bash
# С admin-токеном — ожидается 200/302 (сохранение)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/admin \
  -H "Cookie: admin_token=<ADMIN_TOKEN>" \
  -d "provider=openai&openai_model=gpt-4.1-mini"
```

Ожидаемый результат: `200` или `302` (редирект на `?saved=1`).

---

## 📊 6. Healthcheck-и

| Сервис | Проверка | Где |
|--------|----------|-----|
| `db` | `pg_isready` | compose healthcheck |
| `review-site` | `GET /health` → 200 | compose healthcheck (python urllib) |
| `review-worker` | `healthcheck.py` — freshness `heartbeat.json` | compose healthcheck |

Ручная проверка воркера:

```bash
docker compose exec review-worker python healthcheck.py
```

Ожидаемый результат: `healthcheck OK: heartbeat Ns old`, exit code `0`.

---

## 🛑 7. Остановка и очистка

```bash
# Остановка (данные сохраняются в volumes)
docker compose down

# Полная очистка, включая данные БД и state
docker compose down -v
```

---

## 🌐 8. Адаптация для production

Документ описывает локальное/demo-развёртывание. Для production:

- **TLS / публичный домен:** перед сайтом — обратный прокси (например, Traefik/Caddy) с терминированием TLS; `/admin` — только через HTTPS.
- **Секреты:** не `change-me`; уникальные `WORKER_API_TOKEN`/`ADMIN_TOKEN`/`ADMIN_DEMO_TOKEN`.
- **GigaChat TLS:** `GIGACHAT_CA_BUNDLE` (Russian Trusted Root CA) вместо `ssl.CERT_NONE`.
- **Публичная форма:** рассмотреть токенизацию + квоту (паттерн `web-ui-tokenized-demo-limiter`) и RBAC на `POST /api/reviews` (отложено в v1.0).
- **БД:** резервное копирование `db-data` volume.
- **Telegram:** заполнить `TELEGRAM_BOT_TOKEN` + `TELEGRAM_USER_CHAT_ID` для уведомлений оператору.

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура и путь данных.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты HTTP API.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — безопасность и демо-RBAC.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры LLM-провайдеров.
- [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) — отчёт воспроизводимости в чистом окружении.
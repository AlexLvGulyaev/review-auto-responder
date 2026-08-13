# ✅ DEPLOYMENT_VALIDATION_REPORT.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата валидации:** 2026-08-13
**Валидатор:** автор проекта
**Руководство:** [🚀 DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
**Результат:** ✅ **PASS** — проект полностью воспроизведён с нуля в чистом окружении.

---

## 🧰 1. Условия валидации

| Параметр | Значение |
|----------|----------|
| Окружение | Полностью очищенное: все контейнеры, volumes и образы проекта удалены перед валидацией (`docker compose down -v --rmi all`) |
| Источник | Публичный репозиторий + `DEPLOYMENT_GUIDE.md` |
| Docker | 29.1.3 |
| Docker Compose | v2 2.40.3 |
| Порт сайта | 8010 (`APP_PORT=8010`, порт 8000 на хосте занят другим сервисом) |
| LLM-провайдер | GigaChat (для проверки реального LLM-пути); fallback проверен отдельно |

> 📌 Валидация выполнялась строго по шагам `DEPLOYMENT_GUIDE.md`. Действий, отсутствующих в руководстве, не выполнялось.

---

## 📋 2. Пошаговый отчёт

| # | Шаг DEPLOYMENT_GUIDE | Выполненное действие | Ожидаемый результат | Фактический результат | Статус |
|---|----------------------|----------------------|---------------------|----------------------|--------|
| 1 | §2.1 Получение проекта | `git clone` + `cd` | Проект получен | OK | PASS |
| 2 | §2.2 Файл `.env` | `cp .env.example .env`, заполнение секретов | `.env` заполнен | OK | PASS |
| 3 | §3.1 Запуск | `docker compose up -d --build` | 3 сервиса подняты | db, review-site, review-worker — Up | PASS |
| 4 | §3.2 Состояние | `docker compose ps` | All `Up (healthy)` | All healthy (db 16s, site 11s, worker 5s) | PASS |
| 5 | §3.3 Health сайта | `GET /health` | `200 {"status":"ok"}` | `200 {"status":"ok"}` | PASS |
| 6 | §4.1 Три отзыва | `POST /api/reviews` ×3 (позитив/негатив/нейтраль) | `201` каждый | `201` ×3 | PASS |
| 7 | §4.3 Тональность + ответы | Проверка после цикла опроса | 3 тона определены, 3 ответа, `processed` | Иван=positive, Пётр=negative, Анна=neutral; все `processed` с ответом | PASS |
| 8 | §4.4 Self-reply guard | `GET /api/reviews?status=new` | `[]` (пусто) | `[]` | PASS |
| 9 | §1.3 Серверный фильтр | `?status=new` / `?status=processed` | Фильтрация по статусу | new=`[]`, processed=все | PASS |
| 10 | §5.1 Admin login | `POST /admin/login` (admin + demo) | `303`, cookie установлен | `303` / `303` | PASS |
| 11 | §5.2 Смена провайдера | `POST /admin` (admin) → `gigachat` | `303 ?saved=1`, `config.json` обновлён | `303`, `config.json: provider=gigachat` | PASS |
| 12 | §5.2 Hot-reload | Логи воркера | `Runtime config reloaded` без рестарта | `Runtime config reloaded: provider=gigachat model=GigaChat-Max` | PASS |
| 13 | §5.2 Реальный LLM | Новый отзыв после switch | Ответ сгенерирован GigaChat (не fallback) | «Спасибо большое за тёплые слова! Очень рады, что доставили ваш заказ быстро и аккуратно. Обращайтесь ещё!» | PASS |
| 14 | §5.3 Демо-RBAC (demo) | `POST /admin` с demo-cookie | `403` | `403` | PASS |
| 15 | §5.3 Демо-RBAC (no auth) | `POST /admin` без cookie | `401` | `401` | PASS |
| 16 | §6 Healthcheck воркера | `docker compose exec review-worker python healthcheck.py` | `healthcheck OK`, exit 0 | `healthcheck OK: heartbeat 4s old` | PASS |
| 17 | §6 Healthcheck сервисов | `docker compose ps` | All healthy | All healthy | PASS |

---

## 🧪 3. Fallback-проверка (без LLM-ключа)

На шаге 6–8 валидации активный провайдер был `openai` без `OPENAI_API_KEY` → `ProviderNotConfigured` → воркер ответил словарными fallback-шаблонами по тону. Система не упала, ответы корректны по тональности. Подтверждает устойчивость при отсутствии/сбое провайдера.

---

## 🔐 4. Демо-RBAC

| Сценарий | Результат |
|----------|-----------|
| `GET /admin` без токена | `303` → `/admin/login` |
| `POST /admin/login` (admin) | `303`, cookie `admin_token` (8 ч) |
| `GET /admin` (demo) | `200`, бейдж «👁 Демо-режим: только просмотр» |
| `POST /admin` (demo) | `403` (backend guard `require_admin`) |
| `POST /admin` (no auth) | `401` (backend guard `admin_auth`) |
| `POST /admin` (admin) | `303 ?saved=1` |

Backend — единственный реальный guard: прямой API-вызов с demo-токеном отклоняется на мутации (`403`), обход отключённой UI-кнопки невозможен.

---

## 🎯 5. Критерии готовности (SPEC §7)

| Критерий | Статус |
|----------|--------|
| Единый `docker compose up --build -d` поднимает db + site + worker | ✅ PASS |
| `GET /health` → 200; healthcheck воркера → healthy | ✅ PASS |
| 3 отзыва разной тональности: тон, ответ, `processed` | ✅ PASS |
| Смена провайдера (OpenAI ↔ GigaChat) — ответ через выбранный; сбой → fallback | ✅ PASS |
| `/admin` меняет провайдер/модель/промпт в runtime без рестарта | ✅ PASS |
| Демо-RBAC: admin — мутации; demo — 403; no-auth — 401 | ✅ PASS |
| Промпт из `prompts/v1/system.md`; override через `/admin` | ✅ PASS (код-путь) |
| `?status=new` отдаёт только новые | ✅ PASS |
| Self-reply guard | ✅ PASS |
| Telegram-уведомление (опционально) | ⏸ Пропуск без токена (по плану) |
| Deployment Validation в чистом окружении | ✅ PASS (этот отчёт) |
| Публичная документация самодостаточна | ✅ PASS |

---

## 📌 6. Замечания

- **Порт 8000 занят** на хосте валидации другим сервисом → использован `APP_PORT=8010` (параметр описан в `DEPLOYMENT_GUIDE.md` §2.2). Это не отклонение от руководства — параметр задокументирован.
- **GigaChat TLS:** `ssl.CERT_NONE` (dev/демо) — ожидаемое предупреждение в логах; для prod — `GIGACHAT_CA_BUNDLE` (описано в `EXTERNAL_PROVIDERS.md`).
- **Тональность словарного классификатора:** предсказуема для явных маркеров; отзыв без явных маркеров определяется как `neutral` (по дизайну SPEC §5 — экономия токенов, LLM только для генерации ответа).

---

## ✅ 7. Итог

**Deployment Validation пройдена успешно.** Проект полностью воспроизведён с нуля в чистом окружении исключительно по `DEPLOYMENT_GUIDE.md` и публичному репозиторию: 3 сервиса healthy, путь данных работает (3 отзыва разной тональности обработаны), мультипровайдерность с hot-reload подтверждена реальным запросом к GigaChat, демо-RBAC работает на backend, fallback устойчив. `DEPLOYMENT_GUIDE.md` соответствует статусу Source of Truth воспроизводимости.
# ✅ DEPLOYMENT_VALIDATION_REPORT.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата валидации:** 2026-08-14 (пере-валидация v1.5)
**Валидатор:** автор проекта
**Руководство:** [🚀 DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
**Результат:** ✅ **PASS** — проект полностью воспроизведён с нуля в чистом окружении, включая v1.5 (демо-вход и демо-лимиттер).

> 📌 Эта валидация (2026-08-14) повторяет полную процедуру на свежем клоне
> публичного репозитория и дополняет проверку v1.5-фич: одно-кликового демо-входа
> (`POST /admin/login/demo`) и токенизированного демо-лимиттера (`POST /api/demo/start`,
> квота 5/сессию, 3 уровня, exempt воркера). Предыдущая валидация v1.0 (2026-08-13) —
> в истории git.

---

## 🧰 1. Условия валидации

| Параметр | Значение |
|----------|----------|
| Окружение | Чистый клон публичного репозитория в `/tmp/rar-val` (отдельный compose-project `rar-val`, отдельные контейнеры/volumes/сеть; не затрагивает живое демо) |
| Источник | Публичный репозиторий `github.com/AlexLvGulyaev/review-auto-responder`, commit `a95eec9` (`origin/main`) |
| Руководство | `DEPLOYMENT_GUIDE.md` — шаги выполнялись строго по нему |
| Docker | 29.1.3 |
| Docker Compose | v2 2.40.3 |
| Порт сайта | 8012 (`APP_PORT=8012`, чтобы не конфликтовать с занятыми 8000/8010) |
| LLM-провайдер | GigaChat (`GigaChat-Max`) — реальные секреты из `.env` лаборатории (fallback не тестировался повторно — код неизменен, см. предыдущий отчёт v1.0) |
| Демо-лимиттер | `DEMO_ENABLED=true`, квота 5/сессию, rate-limit 12/мин (5с интервал), 5 сессий/IP/час |

> 📌 Валидация выполнялась строго по шагам `DEPLOYMENT_GUIDE.md`. Действий,
> отсутствующих в руководстве, не выполнялось. `.env` собран из `.env.example` +
> реальные секреты лаборатории + `APP_PORT=8012` + DEMO_*-параметры (из `.env.example`).

---

## 📋 2. Пошаговый отчёт

| # | Шаг DEPLOYMENT_GUIDE | Выполненное действие | Ожидаемый результат | Фактический результат | Статус |
|---|----------------------|----------------------|---------------------|----------------------|--------|
| 1 | §2.1 Получение проекта | `git clone` origin/main → `/tmp/rar-val` | Проект получен | commit `a95eec9` | PASS |
| 2 | §2.2 Файл `.env` | `cp` live-secrets → `.env`, `APP_PORT=8012`, DEMO_* | `.env` заполнен (без `YOUR_`) | OK, 0 placeholder'ов | PASS |
| 3 | §3.1 Запуск | `docker compose up -d --build` | 3 сервиса подняты | db, review-site, review-worker — Up | PASS |
| 4 | §3.2 Состояние | `docker compose ps` | All `Up (healthy)` | All healthy (db 18s, site 12s, worker 7s) | PASS |
| 5 | §3.3 Health сайта | `GET /health` | `200 {"status":"ok"}` | `200 {"status":"ok"}` | PASS |
| 6 | §4.1 Три отзыва | `POST /api/reviews` ×3 с `X-Demo-Token` (позитив/негатив/нейтраль, интервал ≥6с) | `201` каждый | `201` ×3 (rem 4→3→2) | PASS |
| 7 | §4.3 Тональность + ответы | Проверка после цикла опроса | 3 тона, 3 ответа AI, `processed` | Иван=positive, Пётр=negative, Анна=neutral; 3 AI-ответа; все `processed` | PASS |
| 8 | §4.4 Self-reply guard | `GET /api/reviews?status=new` | `[]` | `[]` (worker-ответы тоже `processed`) | PASS |
| 9 | §1.3 Серверный фильтр | `?status=new` / `?status=processed` | Фильтрация по статусу | new=`[]`, processed=all | PASS |
| 10 | §5.1 Admin login | `POST /admin/login` (admin) | `303`, cookie `admin_token` | `303` | PASS |
| 11 | §5.2 Смена провайдера | `POST /admin` (admin) → `gigachat` | `303 ?saved=1`, `config.json` обновлён | `303 ?saved=1`, `config.json: active=gigachat` | PASS |
| 12 | §5.2 Hot-reload | Логи воркера | `Runtime config reloaded` без рестарта | `Runtime config reloaded: active=gigachat fallback=openai model=GigaChat-Max` | PASS |
| 13 | §5.2 Реальный LLM | Новый отзыв после switch | Ответ сгенерирован GigaChat (не fallback) | review #19: `provider=gigachat model=GigaChat-Max status=ok duration_ms=1275` | PASS |
| 14 | §5.2.1 «Проверить» | `POST /admin/test-provider` (gigachat) | `303 ?test=ok`, real-вызов | `303 ?test=ok&prov=gigachat&msg=GigaChat: готов, 474мс · 25ток` | PASS |
| 15 | §5.3 Демо-RBAC (demo) | `POST /admin` с demo-cookie | `403` | `403` | PASS |
| 16 | §5.3 Демо-RBAC (no auth) | `POST /admin` без cookie | `401` | `401` | PASS |
| 17 | §6 Healthcheck воркера | `docker compose exec review-worker python healthcheck.py` | `healthcheck OK`, exit 0 | `healthcheck OK: heartbeat 2s old` | PASS |
| 18 | §6 Healthcheck сервисов | `docker compose ps` | All healthy | All healthy | PASS |

---

## 🆕 3. Валидация v1.5 — демо-вход и демо-лимиттер

### 🆕 3.1. Одно-кликовой демо-вход (`POST /admin/login/demo`)

| Сценарий | Ожидание | Фактически | Статус |
|----------|----------|-----------|--------|
| `POST /admin/login/demo` (demo-токен задан) | `303` → `/admin`, cookie `admin_token` установлен (токен НЕ в браузере) | `303 -> /admin`, cookie set | PASS |
| `POST /admin` под demo-cookie (мутация) | `403` (backend guard `require_admin`) | `403` | PASS |

### 🆕 3.2. Демо-лимиттер публичной формы (`/api/demo`)

| Сценарий | Ожидание | Фактически | Статус |
|----------|----------|-----------|--------|
| `POST /api/demo/start` | `200` + `token` + `requests_limit=5` | `token` (32симв), `requests_limit=5`, `requests_remaining=5` | PASS |
| `POST /api/reviews` ×5 с `X-Demo-Token` (интервал ≥6с) | `201`, `X-Demo-Remaining` 4→0 | `201`×5 (rem 4,3,2,1,0) | PASS |
| 6-й `POST /api/reviews` (квота исчерпана) | `429` | `429` | PASS |
| `POST /api/reviews` с `X-Worker-Token` (exempt) при исчерпанной квоте | `201` (воркер-exempt) | `201` | PASS |
| `GET /api/demo/status` с `X-Demo-Token` | `200`, `is_active=true`, `used=5/limit=5` | `200`, `used=5 limit=5 remaining=0 active=true` | PASS |
| `GET /api/demo/status` без токена | `401` | `401` | PASS |
| Rate-limit: 2-й `POST` подряд (<5с) | `429` (rate-limit, не квота) | `429` (поведение уровня 2) | PASS |

> 📌 Три уровня ограничения подтверждены: (1) квота 5/сессию — 6-я `429`;
> (2) rate-limit 12/мин (5с интервал) — `429` при запросах подряд; (3) sessions/IP/час —
> не нарушен в тесте. Воркер-exempt по `X-Worker-Token` обходит квоту (`201`).

---

## 🧪 4. Fallback-проверка (без LLM-ключа)

Не тестировалась повторно — код fallback-цепочки (active → fallback LLM → словарные
шаблоны) не изменился с v1.0. Результат предыдущей валидации (2026-08-13): при
отсутствии `OPENAI_API_KEY` воркер отвечает словарными шаблонами по тону, система не
падает. См. историю git (отчёт v1.0).

---

## 🔐 5. Демо-RBAC и демо-вход — сводка

| Сценарий | Результат |
|----------|-----------|
| `GET /admin` без токена | `303` → `/admin/login` |
| `POST /admin/login` (admin) | `303`, cookie `admin_token` (8 ч) |
| `POST /admin/login/demo` (demo-токен задан) | `303` → `/admin`, cookie (токен не в браузере) |
| `POST /admin` (demo) | `403` (backend guard `require_admin`) |
| `POST /admin` (no auth) | `401` (backend guard `admin_auth`) |
| `POST /admin` (admin, switch) | `303 ?saved=1` |

Backend — единственный реальный guard: прямой API-вызов с demo-токеном отклоняется
на мутации (`403`); demo-токен при одно-кликовом входе ставится сервером в cookie и не
попадает в браузер (строже запекания в статический бандл).

---

## 🎯 6. Критерии готовности (SPEC §7 + v1.5)

| Критерий | Статус |
|----------|--------|
| Единый `docker compose up --build -d` поднимает db + site + worker | ✅ PASS |
| `GET /health` → 200; healthcheck воркера → healthy | ✅ PASS |
| 3 отзыва разной тональности: тон, ответ, `processed` | ✅ PASS |
| Смена провайдера (OpenAI ↔ GigaChat) — ответ через выбранный; сбой → fallback | ✅ PASS (GigaChat, реальный ответ) |
| `/admin` меняет провайдер/модель/промпт в runtime без рестарта | ✅ PASS (hot-reload) |
| Демо-RBAC: admin — мутации; demo — 403; no-auth — 401 | ✅ PASS |
| **v1.5: одно-кликовой демо-вход** (`POST /admin/login/demo`, cookie, токен не в браузере) | ✅ PASS |
| **v1.5: демо-лимиттер** — квота 5/сессию (6-я `429`), rate-limit, worker-exempt `201` | ✅ PASS |
| Промпт из `system_prompt.md` (файл-SOT); override через `/admin` | ✅ PASS |
| «Проверить» — real-тест провайдера (ключи на воркере) | ✅ PASS |
| `?status=new` отдаёт только новые | ✅ PASS |
| Self-reply guard | ✅ PASS |
| Telegram-уведомление при настроенном токене | ✅ PASS (sent for every review) |
| Deployment Validation в чистом окружении | ✅ PASS (этот отчёт) |
| Публичная документация самодостаточна | ✅ PASS |

---

## 📌 7. Замечания

- **Порт 8000/8010 заняты** на хосте → `APP_PORT=8012` для изоляции от живого демо и
  предыдущей валидации. Параметр задокументирован в `DEPLOYMENT_GUIDE.md` §2.2.
- **Изоляция от живого демо:** чистый клон в `/tmp/rar-val` поднимает собственный
  compose-project `rar-val` (отдельные контейнеры `rar-val-*`, volumes, сеть), без
  `docker-compose.override.yml` → не подключается к прокси-сети Traefik и не затрагивает
  публичное демо. Живое демо работало всё время валидации.
- **GigaChat TLS:** `ssl.CERT_NONE` (dev/демо) — ожидаемое предупреждение; для prod —
  `GIGACHAT_CA_BUNDLE` (см. `EXTERNAL_PROVIDERS.md`).
- **Секреты:** реальные значения из `.env` лаборатории (GigaChat/Telegram/токены) —
  не публикуются (`.env` в `.gitignore`). Валидируется процесс развёртывания, не
  секреты.

---

## ✅ 8. Итог

**Deployment Validation v1.5 пройдена успешно.** Проект полностью воспроизведён с
нуля в чистом окружении (свежий клон публичного репозитория `origin/main` @ `a95eec9`)
исключительно по `DEPLOYMENT_GUIDE.md`: 3 сервиса healthy, путь данных работает (3
отзыва разной тональности обработаны с реальным ответом GigaChat), мультипровайдерность
с hot-reload подтверждена, демо-RBAC работает на backend, **v1.5-фичи валидированы**
(одно-кликовой демо-вход с cookie-без-токена-в-браузере; демо-лимиттер — квота 5/сессию
с 3 уровнями, 6-я `429`, worker-exempt `201`, `GET /api/demo/status` 200/401).
`DEPLOYMENT_GUIDE.md` соответствует статусу Source of Truth воспроизводимости проекта.
# 🎛️ OPERATOR_GUIDE.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата создания:** 2026-08-14
**Последнее обновление:** 2026-08-14
**Статус:** Руководство оператора: как менять поведение системы без программирования, пересборки и рестарта контейнера.

> 🌐 Адреса: живое демо — `https://review-auto-responder.alex-n8n.site/admin`;
> локальный инстанс — `http://localhost:8000/admin` (по [🚀 DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)).

---

## 🔐 1. Доступ к админке

Операторская панель `/admin` защищена двумя токенами (демо-RBAC, см.
[🛡️ SECURITY_NOTES.md](SECURITY_NOTES.md) §2). Вход — два пути на странице логина:

1. **Полный доступ** — введите `ADMIN_TOKEN` в форму. Роль `admin`, бейдж
   «🛠 Администратор» в сайдбаре, кнопка «Сохранить» активна. Cookie `admin_token`
   (8 ч). Это единственная роль, допущенная к мутациям (`POST /admin`).
2. **Демо-доступ (одно-кликовой)** — кнопка «👁 Войти в демо-режим (только
   просмотр)». Сервер сам ставит cookie с `ADMIN_DEMO_TOKEN` — **токен не попадает
   в браузер** (строже запекания в бандл). Роль `demo`, бейдж «👁 Демо-режим»,
   кнопка сохранения отключена. Мутации → `403` на backend.

![Вход в /admin: два пути — форма полного токена и одно-кликовой демо-вход](screenshots/RAR_admin_login.png)

*Страница входа: полный токен или одно-кликовой демо-вход (токен не в браузере).*

> ⚠️ Если `ADMIN_DEMO_TOKEN` не задан в `.env` — кнопка демо-входа показывает
> «Демо-вход отключён» (`?error=demo_unavailable`). Для локальных тестов можно
> `ADMIN_AUTH_ENABLED=false` (все запросы — admin; **только локально**, не для
> публичного демо).

После входа — sidebar-лэйаут (домстиль AIP Dark) с тремя консолями:
**Конфигурация системы** (`/admin`), **📜 Логи** (`/admin/executions`),
**📋 Аудит** (`/admin/audit`). Все панели чтения доступны и admin-, и demo-токеном.

---

## ⚙️ 2. Операторские параметры

Параметры, которые оператор меняет в `/admin` без рестарта. Они пишутся в
`config.json` (shared volume) и `system_prompt.md` (файл-SOT); воркер
hot-reload'ит оба по mtime на следующем цикле опроса.

| Параметр | Где в `/admin` | Что делает | Применение |
|----------|----------------|-----------|-----------|
| **Активный провайдер** | «Настройки LLM и провайдера» | `openai` / `gigachat` — через кого генерируется ответ | Следующий цикл, без рестарта |
| **Fallback провайдер** | «Настройки LLM и провайдера» | LLM-запас на случай сбоя активного | Следующий цикл |
| **Model** (per-провайдер) | Карточка провайдера | `openai_model` / `gigachat_model` | Следующий цикл |
| **Base URL** | Карточка провайдера | OpenAI — редактируемый; GigaChat — read-only из `.env` | Следующий цикл |
| **Temperature / Max tokens** | Карточка провайдера (grid 2) | Per-провайдер | Следующий цикл |
| **Включён** (чекбокс) | Карточка провайдера | Включает провайдер в цепочку fallback | Следующий цикл |
| **Системный промпт** | «Системный промпт» | Тон/стиль ответа — перезаписывает `system_prompt.md` | Следующий цикл |

![Конфиг-консоль /admin: карточки провайдеров, промпт, ряд «Состояние системы»](screenshots/RAR_admin_config.png)

*Конфиг-консоль: две панели side-by-side — провайдеры слева, промпт справа; ряд состояния вверху.*

> 🔒 **Секреты — не операторские параметры.** Ключи LLM (`OPENAI_API_KEY`,
> `GIGACHAT_AUTH_KEY`), токены (`WORKER_API_TOKEN`, `ADMIN_TOKEN`,
> `ADMIN_DEMO_TOKEN`) и `DEMO_*` меняются **только в `.env`** и требуют пересборки
> (см. §8). В `/admin` они не попадают и не перезаписываются.

> 📌 **Тултипы.** Описательные тексты (где живут секреты, как работает файл-SOT)
> спрятаны в CSS-only тултипы (hover) — не загромождают консоль.

---

## 🎛️ 3. Смена провайдера и модели без рестарта

1. Войдите полным токеном (сценарий §1). Откройте конфиг-консоль `/admin`.
2. В панели «Настройки LLM и провайдера» выберите **Активный провайдер** (select)
   и **Fallback провайдер**.
3. В карточках провайдеров (слева направо — OpenAI, GigaChat) задайте per-провайдер
   **Model**, **Temperature**, **Max tokens**, отметьте чекбокс **Включён**.
   Для OpenAI при желании поменяйте **Base URL** (GigaChat — read-only).
4. Нажмите **Сохранить** в хидере консоли → редирект `?saved=1`, нижний toast-flash
   «✓ Конфигурация сохранена».
5. Оставьте новый отзыв (на сайте). В течение цикла опроса воркер подхватит новый
   `config.json` по mtime — **без рестарта контейнера**.

**Ожидаемый результат:** в логах воркера `Runtime config reloaded: active=gigachat
fallback=openai model=GigaChat-Max`; ответ сгенерирован через активный LLM. При
сбое/недоступности активного — сработает fallback LLM, затем словарные шаблоны.
Трейс обработки фиксирует `fallback_reason`.

> 📌 **LLM-fallback-цепочка:** active LLM → fallback LLM (если enabled + configured
> + ≠ active) → словарные шаблоны по тону. Система отвечает даже без LLM-ключей.

---

## ✅ 4. «Проверить» — real-тест провайдера

В каждой карточке провайдера есть кнопка **Проверить**.

1. Нажмите **Проверить** на карточке провайдера.
2. Сайт проксирует запрос (`POST /admin/test-provider`, `require_admin` — demo →
   `403`) во внутренний test-API воркера (`POST /provider-test`, порт
   `WORKER_API_PORT`, **не публикуется на хост**, защищён `X-Worker-Token`).
3. Воркер делает 1-токенный real-вызов LLM и возвращает `{ok, provider, model,
   latency_ms, tokens, message}`.
4. Появляется нижний toast-flash: «✓ Проверка «gigachat»: готов, 474мс, 25ток»
   (или сообщение об ошибке).

![Toast-результат real-теста провайдера: готов, latency, токены](screenshots/RAR_admin_provider_test.png)

*«Проверить»: toast-flash с latency и токенами — ключи остались на воркере.*

**Ключевое:** LLM-ключи живут **только на внутреннем воркере** — публичный сайт
их не получает. Событие пишется в аудит (`admin.provider_test`).

---

## 📝 5. Правка промпта в runtime

Промпт — отдельный файл-SOT `system_prompt.md` на shared volume (не поле в
`config.json`). Правка меняет тон/стиль ответа без деплоя.

1. Войдите полным токеном. В панели «Системный промпт» отредактируйте текст.
2. Нажмите **Сохранить** — текст атомарно перезаписывает `system_prompt.md`
   (`tempfile` + `os.replace`). Если текст не изменился — файл не трогается
   (`prompt_changed=False`).
3. Оставьте новый отзыв. Воркер подхватит новый промпт по mtime на следующем цикле.

![Смена системного промпта: правка и сохранение](screenshots/RAR_admin_prompt_change.png)

*Правка промпта: сохранение перезаписывает файл-SOT.*

![Эффект смены промпта: новый ответ по изменённому промпту](screenshots/RAR_admin_prompt_applied.png)

*После применения: новый отзыв получает ответ по изменённому промпту, без рестарта.*

> 📌 При первом запуске воркер копирует вшитый `worker/prompts/v1/system.md` в
> `/data/runtime/system_prompt.md` (bootstrap), существующий не перезаписывает.
> Аудит фиксирует `prompt_len` + `prompt_changed` + `changed_keys` (без полного
> текста промпта). Архитектура промпта — [📝 PROMPT_ARCHITECTURE.md](PROMPT_ARCHITECTURE.md).

---

## 📊 6. Состояние системы

Блок «Состояние системы» вверху `/admin` (ридонли) + JSON-эндпоинт `GET /admin/status`:

- общий статус (`ok` / `degraded`);
- живая проба БД (`SELECT 1` + latency);
- метрики: отзывы new/processed, трейсы ok/error/started, аудит-счётчик, последняя сессия;
- liveness воркера (`status.json` в shared volume — `worker_alive` = `last_iteration_at`
  свежее `3 × poll_interval`);
- статус провайдеров (булевы флаги «сконфигурирован», активный/fallback/enabled,
  публичный `gigachat_base_url` — без секретов) + последние ошибки трейсов.

```bash
# JSON-снимок (сначала логин для cookie admin_token — см. DEPLOYMENT_GUIDE §5.3)
curl -s -b /tmp/admin_cookies.txt http://localhost:8000/admin/status | python3 -m json.tool
```

---

## 📜 7. Observability — Логи и Аудит (read-only)

Две read-only панели в сайдбаре, доступны и admin-, и demo-токеном:

**📜 Логи** (`/admin/executions`) — master-detail «Запрос → Ответ». Слева: фильтры
(период / статус / тональность) + поиск по `review_id`, карточки 7/стр. Справа:
«Цепочка этапов» (получен отзыв → классификация → Telegram → генерация LLM →
сохранение → отметка обработано), диалектическая пара «Запрос пользователя» /
«Ответ системы», параметры исполнения (провайдер/модель/токены/latency), таймлайн,
JSON-снимок. Шаг `llm_call` несёт `{provider, model, latency_ms, tokens, fallback_reason}`.

![Консоль /admin/executions: master-detail «Запрос → Ответ»](screenshots/RAR_admin_executions.png)

*Логи: список обработок слева, цепочка этапов и Запрос/Ответ справа.*

**📋 Аудит** (`/admin/audit`) — master-detail журнала admin/security-событий. Слева:
фильтры (период / тип действия / тип ресурса — select-списки) + поиск по `user_id`,
карточки 7/стр. Справа: параметры действия, исполнитель, metadata, JSON-снимок
состояния. События: `admin.login_success` (admin/demo), `admin.config_update`,
`admin.provider_test`, `admin.rbac_denied`, `auth.worker_denied`.

![Консоль /admin/audit: master-detail журнала](screenshots/RAR_admin_audit.png)

*Аудит: список событий слева, параметры и JSON-снимок справа.*

> 📌 Навигация в обеих панелях: клик/стрелки ↑/↓ перебирают записи без перезагрузки
> (`history.pushState`); смена страницы = reload. Deep-link: `/admin/executions/{id}`,
> `/admin/audit/{id}`. Сами просмотры панелей **не** создают audit-записей.

---

## 🚫 8. Что требует рестарта (НЕ операторские параметры)

Эти параметры меняются **только в `.env`** и требуют пересборки
(`docker compose up -d --build`) — это не операторские настройки:

- **Секреты:** `OPENAI_API_KEY`, `GIGACHAT_AUTH_KEY`, `WORKER_API_TOKEN`,
  `ADMIN_TOKEN`, `ADMIN_DEMO_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_CHAT_ID`.
- **Демо-лимиттер:** `DEMO_ENABLED`, `DEMO_MAX_REQUESTS_PER_SESSION`,
  `DEMO_SESSION_TTL_MINUTES`, `DEMO_RATE_LIMIT_PER_MINUTE`,
  `DEMO_MAX_SESSIONS_PER_IP_PER_HOUR`.
- **Инфраструктура:** `APP_PORT`, `WORKER_API_PORT`, `WORKER_POLL_INTERVAL`,
  `LOG_LEVEL`, `POSTGRES_*`, `GIGACHAT_CA_BUNDLE`, `ADMIN_AUTH_ENABLED`.

> ⚠️ Развёртывание со значениями-заглушками токенов (`change-me`) в публично
> доступном окружении — уязвимость. Перед публичным запуском задайте уникальные
> значения (см. [🚀 DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) §8.4).

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — главная страница проекта и живое демо.
- [🎬 `docs/E2E_SCENARIOS.md`](E2E_SCENARIOS.md) — сквозные демо-сценарии.
- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура и путь данных.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты HTTP API.
- [📝 `docs/PROMPT_ARCHITECTURE.md`](PROMPT_ARCHITECTURE.md) — архитектура промпта.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — демо-RBAC и безопасность.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры LLM-провайдеров.
- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — развёртывание и smoke-тест.
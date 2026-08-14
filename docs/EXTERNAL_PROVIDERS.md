# 🤖 EXTERNAL_PROVIDERS.md — Review Auto Responder

**Проект:** review-auto-responder
**Дата:** 2026-08-14
**Статус:** исследовательская справка. Source of Truth — официальные доки провайдеров + код адаптеров (правило: внешняя интеграция — официальная документация, не память модели).

Оба провайдера унифицированы на **Chat Completions** (`/chat/completions`, сообщения `system`+`user`). Legacy использовал OpenAI `responses.create`; доработка переводит всё на Chat Completions ради единой абстракции `ResponseProvider`.

---

## 📋 Краткая сводка

| Провайдер | base_url | Модель (по умолчанию) | Auth | Drop-in OpenAI SDK |
|-----------|----------|----------------------|------|--------------------|
| **OpenAI** | `https://api.openai.com/v1` (редактируется) | `gpt-4.1-mini` | `OPENAI_API_KEY` Bearer | да |
| **GigaChat** (Сбер) | `https://gigachat.devices.sberbank.ru/api/v1` | `GigaChat-Max` | OAuth-обмен (адаптер) | нет (отдельный код-путь) |

Ответ — свободный текст (не structured_output): задача генерации ответа на отзыв не требует JSON-схемы.

---

## 🟢 1. OpenAI (OpenAI-compatible)

- **base_url:** `https://api.openai.com/v1` (редактируется в `/admin`, поле `openai_base_url`). Любой OpenAI-compatible endpoint указывается через `base_url`.
- **Модель:** `gpt-4.1-mini` (редактируется в `/admin`, поле `openai_model`).
- **Temperature:** `0.3` по умолчанию (редактируется в `/admin`, поле `openai_temperature`).
- **Max tokens:** `1024` по умолчанию (редактируется в `/admin`, поле `openai_max_tokens`).
- **Auth:** `OPENAI_API_KEY` (`.env`) → Bearer напрямую в `AsyncOpenAI(api_key=…, base_url=…)`.
- **Реализация:** `worker/providers/openai_provider.py` — `OpenAICompatibleProvider`.

> ⚠️ **Доработка v1.0:** модель по умолчанию `gpt-4.1-mini` выбрана как портабельная. Оператор может сменить на любую через `/admin`.

---

## 🤖 2. GigaChat (Сбер) — НЕ drop-in, требуется адаптер

- **base_url:** `https://gigachat.devices.sberbank.ru/api/v1` (в `.env` воркера, read-only в карточке). Фиксированный эндпоинт Сбера с OAuth-обменом и сертификатом Минцифры — константа развёртывания, смена требует правки `.env` и рестарта. У OpenAI `base_url`, в отличие от GigaChat, редактируемый в `/admin` — для OpenAI-compatible endpoints (Azure, локальные LLM, прокси).
- **Модель:** `GigaChat-Max` (редактируется в `/admin`, поле `gigachat_model`).
- **Temperature:** `0.1` по умолчанию (редактируется в `/admin`, поле `gigachat_temperature`).
- **Max tokens:** `500` по умолчанию (редактируется в `/admin`, поле `gigachat_max_tokens`).
- **Auth:** **нельзя** использовать authorization key как статический `api_key`. Нужен обмен authorization key → access token: `POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth`, `Authorization: Basic <auth_key>`, scope `GIGACHAT_API_PERS`; access token (~30 мин) — как `Bearer` в `/chat/completions`.
- **Refresh скрыт:** адаптер `worker/providers/gigachat_adapter.py` запрашивает свежий token **перед каждым запросом** (`_get_access_token`), ручного обновления оператором не требуется.
- **TLS:** сертификат Минцифры РФ. `GIGACHAT_CA_BUNDLE` — проверка; пусто — `ssl.CERT_NONE` (dev/демо; для prod — Russian Trusted Root CA bundle).
- **Реализация:** `gigachat_adapter.py` (синхронный urllib) + `gigachat_provider.py` (async-обёртка через `asyncio.to_thread`). Прямые HTTP-запросы без внешних SDK. `chat_completions(..., max_tokens=None)` добавляет `max_tokens` в payload, если задан.
- **Секрет:** `GIGACHAT_AUTH_KEY` в `.env`.

### 🧪 Статус верификации

- **GigaChat** — end-to-end верифицирован реальным authorization key: OAuth-обмен + `/chat/completions` → корректный ответ на отзыв. Без ключа — `ProviderNotConfigured` → fallback (не падение).
- **«Проверить»** — real-тест через внутренний test-API воркера (`test_connection`, 1-токенный вызов) доступен в `/admin` для обоих провайдеров.

---

## 🔌 3. Fallback (LLM-chain + словарные шаблоны)

Цепочка fallback в `processor.generate_response`: **активный LLM → fallback LLM** (если включён через `*_enabled`, сконфигурирован и отличается от активного) **→ словарные шаблоны** (`build_fallback_response` по определённому тону: позитивный/негативный/нейтральный). `meta` фиксирует провайдера-победителя и `fallback_reason`. Система продолжает отвечать даже без ключей — dict-fallback не падает.

---

## 🔧 4. Источники

- [Sber developers — GigaChat OpenAI-compatible mode](https://developers.sber.ru/docs/ru/gigachat/guides/compatible-openai.md)
- [OpenAI API reference — Chat Completions](https://platform.openai.com/docs/api-reference/chat)
- Код адаптеров: `worker/providers/`.

---

## 📚 Связанные документы

- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура, мультипровайдерность, runtime-config.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — `/admin` поля.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — секреты провайдеров в `.env`.
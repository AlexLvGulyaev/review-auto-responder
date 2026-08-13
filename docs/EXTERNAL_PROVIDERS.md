# 🤖 EXTERNAL_PROVIDERS.md — Review Auto Responder · LLM-провайдеры

**Проект:** review-auto-responder
**Дата:** 2026-08-13
**Статус:** исследовательская справка. Source of Truth — официальные доки провайдеров + код адаптеров (правило APL: внешняя интеграция — официальная документация, не память модели).

Все провайдеры унифицированы на **Chat Completions** (`/chat/completions`, сообщения `system`+`user`) — общем знаменателе OpenAI/GigaChat/Yandex. Legacy использовал OpenAI `responses.create`; доработка переводит всё на Chat Completions ради единой абстракции `ResponseProvider`.

---

## 📋 Краткая сводка

| Провайдер | base_url | Модель (по умолчанию) | Auth | Drop-in OpenAI SDK |
|-----------|----------|----------------------|------|--------------------|
| **OpenAI / «Свой»** | `https://api.openai.com/v1` (редактируется) | `gpt-4.1-mini` | `OPENAI_API_KEY` Bearer | да |
| **GigaChat** (Сбер) | `https://gigachat.devices.sberbank.ru/api/v1` | `GigaChat-Max` | OAuth-обмен (адаптер) | нет (отдельный код-путь) |
| **YandexGPT** | `https://llm.api.cloud.yandex.net/v1` | `gpt://<folder_id>/yandexgpt/latest` | Bearer + `x-folder-id` | частично |

Ответ — свободный текст (не structured_output): задача генерации ответа на отзыв не требует JSON-схемы.

---

## 🟢 1. OpenAI / «Свой» (OpenAI-compatible)

- **base_url:** `https://api.openai.com/v1` (для «Свой» — редактируется в `/admin`, поле `openai_base_url`).
- **Модель:** `gpt-4.1-mini` (редактируется в `/admin`, поле `openai_model`).
- **Auth:** `OPENAI_API_KEY` (`.env`) → Bearer напрямую в `AsyncOpenAI(api_key=…, base_url=…)`.
- **Реализация:** `worker/providers/openai_provider.py` — `OpenAICompatibleProvider`.
- **«Свой»:** тот же класс, `provider=custom`, `openai_base_url` указывает на локальный/корпоративный OpenAI-compatible endpoint.
- **Ограничение `gpt-5-mini`** (если выбран): не принимает `max_tokens` и нестандартную `temperature`. В нашем запросе эти параметры не передаются — портабельно.

> ⚠️ **Доработка v1.0:** модель по умолчанию `gpt-4.1-mini` выбрана как портабельная. Оператор может сменить на любую через `/admin`.

---

## 🤖 2. GigaChat (Сбер) — НЕ drop-in, требуется адаптер

- **base_url:** `https://gigachat.devices.sberbank.ru/api/v1`.
- **Модель:** `GigaChat-Max` (редактируется в `/admin`).
- **Auth:** **нельзя** использовать authorization key как статический `api_key`. Нужен обмен authorization key → access token: `POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth`, `Authorization: Basic <auth_key>`, scope `GIGACHAT_API_PERS`; access token (~30 мин) — как `Bearer` в `/chat/completions`.
- **Refresh скрыт:** адаптер `worker/providers/gigachat_adapter.py` запрашивает свежий token **перед каждым запросом** (`_get_access_token`), ручного обновления оператором не требуется.
- **TLS:** сертификат Минцифры РФ. `GIGACHAT_CA_BUNDLE` — проверка; пусто — `ssl.CERT_NONE` (dev/демо; для prod — Russian Trusted Root CA bundle).
- **Реализация:** `gigachat_adapter.py` (синхронный urllib) + `gigachat_provider.py` (async-обёртка через `asyncio.to_thread`). Прямые HTTP-запросы без внешних SDK.
- **Секрет:** `GIGACHAT_AUTH_KEY` в `.env`.

### 🧪 Статус верификации

- **GigaChat** — end-to-end верифицирован реальным authorization key: OAuth-обмен + `/chat/completions` → корректный ответ на отзыв. Без ключа — `ProviderNotConfigured` → fallback (не падение).

---

## ☁️ 3. YandexGPT (Yandex Foundation Models) — частичный drop-in

- **base_url:** `https://llm.api.cloud.yandex.net/v1` (OpenAI-совместимый `/v1/chat/completions`).
- **Модель:** URI вида `gpt://<folder_id>/yandexgpt/latest` — **имя модели содержит `folder_id`**. В `/admin` модель задаётся с плейсхолдером `<folder_id>`, который подставляется из `yandex_folder_id` (factory).
- **Auth:** `YANDEX_API_KEY` (`.env`) как Bearer (`api_key` в OpenAI SDK) **+** header `x-folder-id: <folder_id>` (через `default_headers`). Опционально `x-data-logging-enabled: false` (запрет логирования промптов).
- **Реализация:** `OpenAICompatibleProvider` с `default_headers={"x-folder-id": folder_id}` и подстановкой `<folder_id>` в `model` (`worker/providers/factory.py`).
- **Секрет:** `YANDEX_API_KEY` в `.env`; `yandex_folder_id` — runtime-параметр в `config.json` через `/admin`.

### 🧪 Статус верификации

- **YandexGPT** — код-путь верифицирован: подстановка `<folder_id>` в URI, формирование `default_headers` (`x-folder-id`), routing на `llm.api.cloud.yandex.net`. End-to-end — при наличии API-ключа Yandex + `folder_id`. Параметры сверены по официальной документации Yandex AI Studio (OpenAI-compatibility) и реализации langchain-yandex.

> ℹ️ Страница `aistudio.yandex.ru` может отдавать капчу при автоматическом запросе; сверка — по англ. доке и реализации langchain-yandex. Перед боевым подключением — перепроверить base_url/header в браузере.

---

## 🔌 4. Fallback (без провайдера / при сбое)

Если активный провайдер не настроен (`ProviderNotConfigured` — нет ключа), сбой API или пустой ответ — `processor.generate_response` переходит на `build_fallback_response`: словарные шаблоны по определённому тону (позитивный/негативный/нейтральный). Система продолжает отвечать даже без ключа.

---

## 🔧 5. Источники

- [Sber developers — GigaChat OpenAI-compatible mode](https://developers.sber.ru/docs/ru/gigachat/guides/compatible-openai.md)
- [Yandex AI Studio — OpenAI compatibility](https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/openai-compatibility)
- [langchain-yandex chat_models.ts](https://github.com/langchain-ai/langchainjs-community/blob/main/libs/langchain-yandex/src/chat_models.ts)
- Код адаптеров: `worker/providers/`.

---

## 📚 Связанные документы

- [🏗️ `docs/ARCHITECTURE.md`](ARCHITECTURE.md) — архитектура, мультипровайдерность, runtime-config.
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — `/admin` поля.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — секреты провайдеров в `.env`.
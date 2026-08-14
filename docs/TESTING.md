# 🧪 TESTING.md — Review Auto Responder

**Проект:** review-auto-responder
**Версия:** 1.0
**Дата:** 2026-08-14
**Статус:** Active — Deployment Validation пройдена (v1.5), ручные E2E-сценарии, программные smoke-проверки конвейера.

> 📌 **Важно.** У проекта нет pytest-набора unit/integration-тестов. Проверка ведётся
> на четырёх уровнях: воспроизведение с нуля (L1), ручные сквозные сценарии (L2),
> программные smoke-проверки детерминированного ядра (L3), верификация провайдеров
> реальными LLM-вызовами (L4). Почему так — см. §7.

---

## 🎯 1. Назначение

Зафиксировать, как и на каких уровнях проверяется работоспособность проекта.
Цель — воспроизводимая уверенность, что конвейер «опрос → классификация →
AI-ответ → уведомление» работает, мультипровайдерность и демо-RBAC функционируют,
а развёртывание воспроизводимо с нуля по документации.

---

## 🧩 2. Уровни проверки

| Уровень | Что проверяет | Внешние вызовы | Где описан | Стоимость |
|---------|---------------|---------------|------------|-----------|
| **L1 — Deployment Validation** | Воспроизведение с нуля в чистом окружении по `DEPLOYMENT_GUIDE` | LLM (GigaChat) | `DEPLOYMENT_VALIDATION_REPORT.md` | Средняя (развернуть + прогнать) |
| **L2 — E2E-сценарии (ручные)** | Сквозные потоки в браузере: сайт + `/admin` + Telegram | LLM | `E2E_SCENARIOS.md` (13 сценариев) | Низкая (браузер) |
| **L3 — Smoke-проверки (программно)** | Детерминированное ядро: health, фильтры, demo-RBAC, demo-лимиттер — без LLM-генерации | Нет (или fallback) | §4 ниже | ~0 |
| **L4 — Верификация провайдеров** | Реальные LLM-вызовы: смена провайдера, ответ, «Проверить» | LLM (active+fallback) | `EXTERNAL_PROVIDERS.md`, §4 | По токенам |

### 🧪 2.1. L1 — Deployment Validation

Воспроизведение полностью работоспособного экземпляра с нуля исключительно по
`DEPLOYMENT_GUIDE.md` в чистом окружении (новый VPS/VM/чистый хост; не рабочее
окружение разработчика). Критерий готовности к публикации. Каждый шаг — PASS/FAIL
в `DEPLOYMENT_VALIDATION_REPORT.md`. На v1.5 — 18 шагов + v1.5-фичи (демо-вход,
демо-лимиттер), все PASS.

### 🎬 2.2. L2 — E2E-сценарии (ручные)

13 сквозных сценариев в браузере по [🎬 `E2E_SCENARIOS.md`](E2E_SCENARIOS.md):
публичный сайт (демо-квота, отзыв, AI-ответ, исчерпание), операторская панель
(вход, демо-RBAC, смена провайдера, «Проверить», правка промпта, Логи, Аудит),
Telegram-уведомление. Сценарии, требующие реального LLM-ответа, проверяются
> оператором на живом демо.

### ⚙️ 2.3. L3 — Smoke-проверки (программно, без LLM)

Детерминированное ядро проверяется curl-командами без расхода токенов на
генерацию: health-эндпоинты, серверный фильтр `?status=`, self-reply guard,
demo-RBAC (403/401), demo-лимиттер (квота/rate-limit/exempt/status). Fallback
(словарные шаблоны) проверяется без LLM-ключа. Команды — §4.

### 🔌 2.4. L4 — Верификация провайдеров

Реальные LLM-вызовы по провайдерам (OpenAI/GigaChat): смена активного провайдера
в runtime → ответ через выбранный → проверка `fallback_reason` при сбое активного;
кнопка «Проверить» (1-токенный real-вызов, latency/токены). Гейтится секретами в
`.env`. Метрики пишутся в execution-трейс (`provider/model/latency_ms/tokens`).

---

## 🛠️ 3. Требования к окружению

| Переменная | Назначение | Когда нужна |
|------------|-----------|-------------|
| `WORKER_API_TOKEN` | Общий токен site↔worker; exempt воркера от демо-квоты | Всегда |
| `ADMIN_TOKEN` / `ADMIN_DEMO_TOKEN` | Полный / read-only доступ к `/admin` | L1–L4 |
| `OPENAI_API_KEY` / `GIGACHAT_AUTH_KEY` | LLM-провайдеры (один из них) | L1, L2 (ответ), L4; L3 — не нужно |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_USER_CHAT_ID` | Уведомления оператору | Сценарий Telegram (опц.) |
| `DEMO_ENABLED=true` | Демо-лимиттер публичной формы | L3 (demo-лимиттер), L1 |
| `ADMIN_AUTH_ENABLED=false` | Отключить auth (все — admin) | Только локальные тесты L3 |

> ⚠️ L3 можно прогонять без LLM-ключей: fallback отвечает словарными шаблонами
> по тону, система не падает. L1/L2/L4 требуют хотя бы один провайдер.

---

## ▶️ 4. Команды проверки

```bash
# 0. Развёртывание
cp .env.example .env            # заполнить секреты (минимум — токены)
docker compose up -d --build
docker compose ps                # db / review-site / review-worker — Up (healthy)

# 1. Health (L3)
curl -s http://localhost:8000/health                              # {"status":"ok"}

# 2. Smoke: 3 отзыва разной тональности через демо-сессию (L3 + L2)
TOKEN=$(curl -s -X POST http://localhost:8000/api/demo/start \
  -H 'Content-Type: application/json' -d '{}' | grep -oP '"token":"\K[^"]+')
curl -s -X POST http://localhost:8000/api/reviews -H "Content-Type: application/json" \
  -H "X-Demo-Token: $TOKEN" -d '{"name":"Иван","text":"Отличный сервис, спасибо!"}' ; echo
# (повторить для негативного/нейтрального с интервалом ≥6 c — rate-limit 12/мин)

# 3. Дождаться обработки и проверить (L3)
curl -s "http://localhost:8000/api/reviews?status=new" | python3 -m json.tool   # [] — self-reply guard
curl -s "http://localhost:8000/api/reviews?status=processed" | python3 -m json.tool

# 4. Демо-RBAC (L3)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/admin/login/demo -c /tmp/d.txt   # 303
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/admin -b /tmp/d.txt \
  -d "active_provider=openai&fallback_provider=gigachat&openai_model=x&openai_base_url=x&openai_temperature=0.3&openai_max_tokens=1&gigachat_model=x&gigachat_temperature=0.1&gigachat_max_tokens=1"   # 403

# 5. Демо-лимиттер (L3)
TOKEN=$(curl -s -X POST http://localhost:8000/api/demo/start -H 'Content-Type: application/json' -d '{}' | grep -oP '"token":"\K[^"]+')
for i in 1 2 3 4 5 6; do sleep 6; \
  curl -s -o /dev/null -w "POST #$i -> %{http_code}\n" -X POST http://localhost:8000/api/reviews \
  -H "Content-Type: application/json" -H "X-Demo-Token: $TOKEN" -d '{"name":"t","text":"q"}'; done   # 201×5 + 429
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/reviews \
  -H "Content-Type: application/json" -H "X-Worker-Token: $WAPI" -d '{"name":"w","text":"exempt"}'   # 201 — worker exempt
curl -s http://localhost:8000/api/demo/status -H "X-Demo-Token: $TOKEN" | python3 -m json.tool   # used=5/limit=5

# 6. Смена провайдера без рестарта (L4) — admin-логин сначала
curl -s -c /tmp/a.txt -X POST http://localhost:8000/admin/login -d "admin_token=<ADMIN_TOKEN>"
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/admin -b /tmp/a.txt \
  -d "active_provider=gigachat&fallback_provider=openai&openai_model=gpt-4.1-mini&openai_base_url=https://api.openai.com/v1&openai_temperature=0.3&openai_max_tokens=1024&gigachat_model=GigaChat-Max&gigachat_temperature=0.1&gigachat_max_tokens=500&openai_enabled=on&gigachat_enabled=on"   # 302 ?saved=1
docker compose logs --tail=5 review-worker   # Runtime config reloaded: active=gigachat ... model=GigaChat-Max

# 7. «Проверить» провайдер (L4)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/admin/test-provider -b /tmp/a.txt -d "provider=gigachat"   # 302 ?test=ok...

# 8. Healthcheck воркера (L3)
docker compose exec review-worker python healthcheck.py   # healthcheck OK: heartbeat Ns old, exit 0
```

> 📌 Полные последовательности и ожидаемые результаты —
> [🚀 `DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) §3–6;
> поэтапный PASS/FAIL — [✅ `DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md).

---

## 💰 5. Стоимость и цель каждого уровня

| Уровень | Цель | Ресурсы | Когда запускать |
|---------|------|---------|------------------|
| **L1** | Доказать воспроизводимость с нуля | Полное развёртывание + LLM-токены | Перед публикацией / после изменений развёртывания |
| **L2** | Подтвердить пользовательские потоки | Браузер + LLM | Перед релизом демо / регрессионно |
| **L3** | Дёшево проверить ядро без токенов | curl, 0 LLM | После каждого изменения кода; CI |
| **L4** | Подтвердить работу провайдеров | LLM-токены (active+fallback) | При смене/добавлении провайдера |

> 📌 **Дешёвая классификация** — экономический рычаг L3/L4: тон определяется
> словарём без LLM, поэтому smoke-проверки классификации не стоят токенов. LLM
> расходуется только на генерацию ответа (L2/L4).

---

## 🔒 6. Изоляция и безопасность

- **Чистое окружение для L1:** новый VPS/VM/чистый хост; **запрещено** использовать
  рабочее окружение разработчика как доказательство воспроизводимости. Действия,
  отсутствующие в `DEPLOYMENT_GUIDE`, не выполняются (иначе Validation = FAIL).
- **Секреты:** L1/L2/L4 гейтятся `.env`; в репозитории — только `.env.example` с
> placeholder'ами `YOUR_*`. Ключи LLM не публикуются.
- **Демо-лимиттер** изолирует публичную форму (квота 5/сессию) — см.
> [🛡️ `SECURITY_NOTES.md`](SECURITY_NOTES.md) §4.
- **Isolated compose-project для Validation:** клон в отдельной директории →
> собственные контейнеры/volumes/сеть/порт; не затрагивает живое демо (см.
> замечания в `DEPLOYMENT_VALIDATION_REPORT.md`).

---

## 🚀 7. CI/CD рекомендации (дорожная карта)

| Стадия | Команда/действие | Условие успеха |
|--------|------------------|----------------|
| Build | `docker compose up -d --build` | 3 сервиса `Up (healthy)` |
| L3 smoke | curl-команды §4 (1,3,4,5,8) | Все ожидаемые HTTP-коды |
| L1 validation | Клон + развёртывание по `DEPLOYMENT_GUIDE` в чистом env | 18/18 PASS + v1.5-фичи |
| L2/L4 | Ручные сценарии на живом демо | Все сценарии — ожидаемый результат |

---

## 🗓️ 8. Что отсутствует и почему (roadmap)

- **pytest-набор unit/integration отсутствует.** Ядро (классификатор тона, guard'ы,
  demo-лимиттер, runtime-config migration) проверяется программно (L3) и сквозно
  (L1/L2). Следующий шаг зрелости — добавить pytest с маркерами
  `unit`/`integration`/`expensive` по конвенции проекта; L3-команды §4 — готовые
  кандидаты в параметризованные тесты.
- **Нагрузочное тестирование** не проводилось; демо-лимиттер (3 уровня) — защита
  публичной формы, не бенчмарк пропускной способности.
- **Скриншотные E2E (Playwright/Selenium)** отсутствуют; визуальная проверка UI —
  оператором в браузере (ограничение моделей без image-input на этапе разработки).

> 📌 Эти ограничения честно зафиксированы, а не скрыты. L1 (Deployment Validation)
> — текущий основной гейт публикации; pytest — следующий уровень зрелости.

---

## 📚 9. Связанные документы

- [🚀 `docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) — воспроизводимое развёртывание (SOT для L1).
- [✅ `docs/DEPLOYMENT_VALIDATION_REPORT.md`](DEPLOYMENT_VALIDATION_REPORT.md) — отчёт L1 (PASS/FAIL по шагам).
- [🎬 `docs/E2E_SCENARIOS.md`](E2E_SCENARIOS.md) — сквозные сценарии L2.
- [🎛️ `docs/OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — операторские параметры и runtime-config.
- [🛡️ `docs/SECURITY_NOTES.md`](SECURITY_NOTES.md) — демо-RBAC и демо-лимиттер.
- [🤖 `docs/EXTERNAL_PROVIDERS.md`](EXTERNAL_PROVIDERS.md) — параметры LLM-провайдеров (L4).
- [🔌 `docs/API_CONTRACT.md`](API_CONTRACT.md) — контракты HTTP API.

---

## 📜 10. История изменений

| Дата | Версия | Изменение |
|------|--------|-----------|
| 2026-08-14 | 1.0 | Стратегия тестирования: 4 уровня (L1–L4), smoke-команды, roadmap pytest. |
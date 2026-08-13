"""Внутренний test-HTTP-сервер воркера для кнопки «Проверить» в /admin.

Минимальный сервер на stdlib `asyncio.start_server` — БЕЗ новых зависимостей.
Порт (`worker_api_port`, по умолч. 8001) НЕ публикуется на хост: сайт обращается
к воркеру по DNS сервиса compose (`http://review-worker:8001`) внутри общей сети.
Эндпоинт `POST /provider-test` защищён header `X-Worker-Token` (= WORKER_API_TOKEN).

Назначение — real-проверка доступности LLM-провайдера. Секреты (ключи API) живут
только на воркере; публичный сайт их не получает — он лишь проксирует запрос сюда
(см. site/app/api/admin.py `POST /admin/test-provider`).

Ответ JSON: `{ok, provider, model, latency_ms, tokens, message}`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from config import get_settings
from providers import ProviderNotConfigured, build_provider_for_key


logger = logging.getLogger("worker.api")

_SETTINGS = get_settings()

# Чтение тела ограничено небольшим лимитом — payload это всегда короткий JSON
# `{"provider":"openai"|"gigachat"}`.
_MAX_BODY_BYTES = 4096


def _json_response(status: int, payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return (
        f"HTTP/1.1 {status} OK\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("utf-8") + body


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str], bytes]:
    """Разобрать HTTP-запрос: (method, path, headers, body)."""
    request_line = await reader.readline()
    if not request_line:
        raise ConnectionError("empty request")
    parts = request_line.decode("iso-8859-1").split()
    if len(parts) < 2:
        raise ConnectionError("malformed request line")
    method, path = parts[0], parts[1]

    headers: dict[str, str] = {}
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break
        decoded = line.decode("iso-8859-1").rstrip()
        if ":" in decoded:
            name, _, value = decoded.partition(":")
            headers[name.strip().lower()] = value.strip()

    body = b""
    length = int(headers.get("content-length", "0") or "0")
    if length > 0:
        body = await reader.read(min(length, _MAX_BODY_BYTES))
    return method, path, headers, body


async def _handle_provider_test(body: bytes) -> bytes:
    """POST /provider-test → build_provider_for_key + test_connection → JSON."""
    token = _SETTINGS.worker_api_token
    # Аутентификация проверяется в dispatch по header; сюда попадаем только
    # после успешной проверки — собираем результат теста.
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response(400, {"ok": False, "message": "невалидный JSON в теле запроса"})

    provider_key = (payload.get("provider") or "").strip().lower()
    if provider_key not in ("openai", "gigachat"):
        return _json_response(400, {"ok": False, "message": "поле provider должно быть openai или gigachat"})

    try:
        provider = build_provider_for_key(provider_key)
    except ProviderNotConfigured as exc:
        return _json_response(200, {
            "ok": False,
            "provider": provider_key,
            "model": None,
            "latency_ms": None,
            "tokens": None,
            "message": f"провайдер не настроен: {exc}",
        })

    try:
        result = await provider.test_connection()
    except Exception as exc:  # noqa: BLE001
        logger.exception("provider-test %s failed: %s", provider_key, exc)
        return _json_response(200, {
            "ok": False,
            "provider": provider_key,
            "model": provider.model_name,
            "latency_ms": None,
            "tokens": None,
            "message": f"ошибка запроса: {exc}"[:500],
        })

    return _json_response(200, {
        "ok": bool(result.get("ok")),
        "provider": provider_key,
        "model": provider.model_name,
        "latency_ms": result.get("latency_ms"),
        "tokens": result.get("tokens"),
        "message": result.get("message", "ok" if result.get("ok") else "не удалось"),
    })


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Обработать одно соединение: разбор запроса → маршрутизация → ответ."""
    try:
        method, path, headers, body = await _read_request(reader)
    except (ConnectionError, asyncio.IncompleteReadError, ValueError):
        writer.close()
        await writer.wait_closed()
        return

    try:
        # Маршрутизация.
        if method == "POST" and path.rstrip("/") == "/provider-test":
            # Аутентификация по X-Worker-Token.
            if headers.get("x-worker-token") != _SETTINGS.worker_api_token:
                resp = _json_response(401, {"ok": False, "message": "невалидный или отсутствующий X-Worker-Token"})
                writer.write(resp)
                await writer.drain()
                return
            resp = await _handle_provider_test(body)
            writer.write(resp)
            await writer.drain()
            return

        # healthcheck без auth — для внутреннего liveness (не несёт секретов).
        if method == "GET" and path.rstrip("/") == "/health":
            resp = _json_response(200, {"ok": True, "service": "worker-test-api"})
            writer.write(resp)
            await writer.drain()
            return

        writer.write(_json_response(404, {"ok": False, "message": "not found"}))
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def serve_test_api() -> None:
    """Запустить внутренний test-HTTP-сервер на `worker_api_port`.

    Запускается параллельно с poll_loop в одном asyncio-цикле (worker.main).
    Сервер слушает только внутри compose-сети; порт не публикуется на хост.
    """
    port = _SETTINGS.worker_api_port
    server = await asyncio.start_server(_handle_client, host="0.0.0.0", port=port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    logger.info("Worker test-API listening on %s (internal, POST /provider-test)", addrs)
    async with server:
        await server.serve_forever()
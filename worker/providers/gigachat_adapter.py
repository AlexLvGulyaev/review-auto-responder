from __future__ import annotations

"""GigaChat (Сбер) адаптер — прямой HTTP, OAuth-обмен токена per-request.

GigaChat не является drop-in OpenAI-совместимым провайдером: вместо статического
API-ключа используется authorization key, который обменивается на короткоживущий
access token (~30 мин) через `/oauth` endpoint с HTTP Basic. Этот адаптер
запрашивает свежий access token перед каждым запросом — refresh скрыт под
капотом, ручного обновления оператором не требуется.

Возвращает сырой текст ответа — без structured_output (GigaChat не поддерживает
json_schema strict).

TLS: эндпоинты GigaChat используют сертификат Минцифры РФ. Если задан
`GIGACHAT_CA_BUNDLE` — используется для проверки; иначе проверка отключается
(`ssl.CERT_NONE`) — приемлемо для dev/демо, для prod рекомендуется CA-bundle.
"""

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)


class GigaChatError(RuntimeError):
    """Ошибка GigaChat-адаптера (токен/сеть/HTTP)."""


def build_ssl_context(ca_bundle: Optional[str] = None) -> ssl.SSLContext:
    """SSL-контекст для GigaChat. С CA-bundle — проверка; без него — CERT_NONE."""
    if ca_bundle and os.path.isfile(ca_bundle):
        ctx = ssl.create_default_context(cafile=ca_bundle)
        logger.info("GigaChat TLS: using CA bundle %s", ca_bundle)
        return ctx
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    logger.warning(
        "GigaChat TLS: CA bundle not set (%r), certificate verification DISABLED "
        "(ssl.CERT_NONE). Acceptable for dev/demo; set GIGACHAT_CA_BUNDLE for prod.",
        ca_bundle,
    )
    return ctx


class GigaChatAdapter:
    """Минимальный синхронный GigaChat-клиент (прямые HTTP-запросы)."""

    def __init__(
        self,
        *,
        base_url: str,
        token_url: str,
        scope: str,
        auth_key: str,
        ca_bundle: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        if not auth_key:
            raise GigaChatError("GIGACHAT_AUTH_KEY не задан — GigaChat не настроен.")
        self.base_url = base_url.rstrip("/")
        self.token_url = token_url
        self.scope = scope
        self.auth_key = auth_key
        self.timeout = timeout
        self._ssl_context = build_ssl_context(ca_bundle)

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        data: Optional[bytes] = None,
    ) -> dict[str, Any]:
        request_headers = dict(headers or {})
        request_headers.setdefault("Accept", "application/json")
        req = urllib.request.Request(
            url, method=method, data=data, headers=request_headers
        )
        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            raise GigaChatError(
                f"GigaChat HTTP {exc.code} {exc.reason}: {detail[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GigaChatError(f"GigaChat network error: {exc.reason}") from exc

    def _get_access_token(self) -> str:
        headers = {
            "Authorization": f"Basic {self.auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = f"scope={self.scope}".encode("utf-8")
        response = self._request_json(
            self.token_url, method="POST", headers=headers, data=data
        )
        access_token = response.get("access_token")
        if not access_token:
            raise GigaChatError(
                f"GigaChat token response missing access_token: {response}"
            )
        return access_token

    def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """Запрос `/chat/completions`. Возвращает {content, usage, model}.

        messages — список {role, content} (поддерживаются system/user/assistant),
        как в OpenAI Chat Completions. Без response_format — портабельно
        (GigaChat не поддерживает json_schema strict). max_tokens опционален.
        """
        started = time.perf_counter()
        access_token = self._get_access_token()
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        response = self._request_json(url, method="POST", headers=headers, data=data)

        choices = response.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""
        usage = response.get("usage") or {}
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "content": content or "",
            "model": response.get("model", model),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            "latency_ms": latency_ms,
        }
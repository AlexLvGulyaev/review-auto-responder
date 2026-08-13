from __future__ import annotations

import asyncio
import logging
import time

from providers.base import ResponseProvider
from providers.gigachat_adapter import GigaChatAdapter, GigaChatError


logger = logging.getLogger("worker.provider.gigachat")


class GigaChatProvider(ResponseProvider):
    """GigaChat (Сбер) — OAuth-адаптер, async-обёртка через asyncio.to_thread.

    Адаптер синхронный (urllib); обработчик async — обёртка to_thread не блокирует
    цикл. access token запрашивается per-request (refresh скрыт).
    temperature/max_tokens — из runtime-config (через /admin).
    """

    def __init__(
        self,
        *,
        auth_key: str,
        base_url: str,
        token_url: str,
        scope: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 500,
        ca_bundle: str = "",
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._adapter = GigaChatAdapter(
            base_url=base_url,
            token_url=token_url,
            scope=scope,
            auth_key=auth_key,
            ca_bundle=ca_bundle or None,
        )
        self.last_usage: int | None = None

    @property
    def name(self) -> str:
        return "gigachat"

    @property
    def model_name(self) -> str:
        return self._model

    async def _chat(self, system_prompt: str, user_text: str, max_tokens: int) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        result = await asyncio.to_thread(
            self._adapter.chat_completions,
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=max_tokens,
        )
        usage = result.get("usage") or {}
        self.last_usage = usage.get("total_tokens")
        return (result.get("content") or "").strip()

    async def generate(
        self,
        system_prompt: str,
        user_text: str,
        max_tokens: int | None = None,
    ) -> str:
        return await self._chat(system_prompt, user_text, max_tokens if max_tokens is not None else self._max_tokens)

    async def test_connection(self) -> dict:
        started = time.perf_counter()
        try:
            text = await self._chat("You are a connection test proxy.", "Reply with the single word: ok", 1)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "ok": True,
                "latency_ms": latency_ms,
                "tokens": self.last_usage,
                "message": f"GigaChat: готов, модель {self._model}, {latency_ms} мс",
            }
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": False, "latency_ms": latency_ms, "tokens": None, "message": f"GigaChat: ошибка — {exc}"}
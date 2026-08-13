from __future__ import annotations

import asyncio
import logging

from providers.base import ResponseProvider
from providers.gigachat_adapter import GigaChatAdapter, GigaChatError


logger = logging.getLogger("worker.provider.gigachat")


class GigaChatProvider(ResponseProvider):
    """GigaChat (Сбер) — OAuth-адаптер, async-обёртка через asyncio.to_thread.

    Адаптер синхронный (urllib); обработчик async — обёртка to_thread не блокирует
    цикл. access token запрашивается per-request (refresh скрыт).
    """

    def __init__(
        self,
        *,
        auth_key: str,
        base_url: str,
        token_url: str,
        scope: str,
        model: str,
        ca_bundle: str = "",
    ) -> None:
        self._model = model
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

    async def generate(self, system_prompt: str, user_text: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        result = await asyncio.to_thread(
            self._adapter.chat_completions, model=self._model, messages=messages
        )
        usage = result.get("usage") or {}
        self.last_usage = usage.get("total_tokens")
        return (result.get("content") or "").strip()
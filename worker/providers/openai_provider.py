from __future__ import annotations

import logging
import time
from typing import Any

from openai import AsyncOpenAI

from providers.base import ResponseProvider


logger = logging.getLogger("worker.provider.openai")


class OpenAICompatibleProvider(ResponseProvider):
    """OpenAI Chat Completions — работает для OpenAI и OpenAI-compatible endpoint.

    base_url/temperature/max_tokens берутся из runtime-config (через /admin),
    что позволяет указать любой OpenAI-совместимый endpoint и подобрать
    параметры генерации без рестарта.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        default_headers: dict[str, str] | None = None,
        label: str = "openai",
    ) -> None:
        self._model = model
        self._label = label
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers)
        self.last_usage: int | None = None

    @property
    def name(self) -> str:
        return self._label

    @property
    def model_name(self) -> str:
        return self._model

    async def _chat(self, system_prompt: str, user_text: str, max_tokens: int) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=self._temperature,
            max_tokens=max_tokens,
        )
        self.last_usage = response.usage.total_tokens if response.usage else None
        choice = response.choices[0] if response.choices else None
        content: Any = choice.message.content if choice and choice.message else ""
        return (content or "").strip()

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
                "message": f"OpenAI: готов, модель {self._model}, {latency_ms} мс",
            }
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": False, "latency_ms": latency_ms, "tokens": None, "message": f"OpenAI: ошибка — {exc}"}
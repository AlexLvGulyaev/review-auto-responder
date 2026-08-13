from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from providers.base import ResponseProvider


logger = logging.getLogger("worker.provider.openai")


class OpenAICompatibleProvider(ResponseProvider):
    """OpenAI Chat Completions — работает для OpenAI и OpenAI-compatible endpoint.

    base_url берётся из runtime-config (через /admin), что позволяет указать
    любой OpenAI-совместимый endpoint.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        default_headers: dict[str, str] | None = None,
        label: str = "openai",
    ) -> None:
        self._model = model
        self._label = label
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers)
        self.last_usage: int | None = None

    @property
    def name(self) -> str:
        return self._label

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(self, system_prompt: str, user_text: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        self.last_usage = response.usage.total_tokens if response.usage else None
        choice = response.choices[0] if response.choices else None
        content: Any = choice.message.content if choice and choice.message else ""
        return (content or "").strip()
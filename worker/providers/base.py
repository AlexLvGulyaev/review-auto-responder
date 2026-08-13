from __future__ import annotations

from abc import ABC, abstractmethod


class ResponseProvider(ABC):
    """Единый интерфейс генерации ответа для всех LLM-провайдеров.

    Унификация на Chat Completions (общий знаменатель OpenAI/GigaChat).
    Legacy использовал OpenAI `responses.create` — доработка переводит все
    провайдеры на Chat Completions ради единой абстракции.

    `model_name` — имя модели для observability/execution-трассировки.
    `last_usage` — количество токенов последнего запроса (None, если провайдер
    не вернул usage); обновляется в `generate`.
    """

    last_usage: int | None = None

    @abstractmethod
    async def generate(self, system_prompt: str, user_text: str) -> str:
        """Сгенерировать ответ на отзыв. Возвращает пустую строку при пустом ответе."""
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError
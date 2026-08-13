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

    Per-provider runtime-параметры (model/temperature/max_tokens) задаются в
    config.json через /admin; применяются в runtime без рестарта.
    """

    last_usage: int | None = None

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_text: str,
        max_tokens: int | None = None,
    ) -> str:
        """Сгенерировать ответ на отзыв.

        `max_tokens` — опц. override сконфигурированного лимита (используется
        тестом «Проверить» для дешёвого 1-токенного вызова). Возвращает пустую
        строку при пустом ответе.
        """
        raise NotImplementedError

    @abstractmethod
    async def test_connection(self) -> dict:
        """Минимальный real-вызов для проверки доступности провайдера.

        Возвращает `{ok: bool, latency_ms: int, tokens: int|None, message: str}`.
        Используется эндпоинтом `/provider-test` воркера (кнопка «Проверить»).
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError
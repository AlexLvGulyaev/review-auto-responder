from __future__ import annotations

import logging

from config import get_settings
from providers.base import ResponseProvider
from providers.gigachat_provider import GigaChatProvider
from providers.openai_provider import OpenAICompatibleProvider
from runtime_config import get_runtime_config


logger = logging.getLogger("worker.provider.factory")


class ProviderNotConfigured(RuntimeError):
    """Активный провайдер не настроен (нет ключа/параметров)."""


def build_provider() -> ResponseProvider:
    """Собрать провайдер по runtime-config (через /admin, без рестарта).

    Два провайдера: openai и gigachat. Секреты берутся из .env (settings),
    runtime-параметры (provider/модели/base_url) — из config.json. Если ключ
    активного провайдера не задан — ProviderNotConfigured (processor уйдёт в
    fallback).
    """
    settings = get_settings()
    runtime = get_runtime_config()
    provider = runtime.get("provider", "openai")

    if provider == "gigachat":
        if not settings.gigachat_auth_key:
            raise ProviderNotConfigured("GIGACHAT_AUTH_KEY не задан")
        model = runtime.get("gigachat_model", "GigaChat-Max")
        return GigaChatProvider(
            auth_key=settings.gigachat_auth_key,
            base_url=settings.gigachat_base_url,
            token_url=settings.gigachat_token_url,
            scope=settings.gigachat_scope,
            model=model,
            ca_bundle=settings.gigachat_ca_bundle,
        )

    # openai — OpenAI SDK + base_url из runtime (для OpenAI-compatible endpoint).
    if not settings.openai_api_key:
        raise ProviderNotConfigured("OPENAI_API_KEY не задан")
    model = runtime.get("openai_model", "gpt-4.1-mini")
    base_url = runtime.get("openai_base_url", "https://api.openai.com/v1")
    return OpenAICompatibleProvider(
        api_key=settings.openai_api_key,
        base_url=base_url,
        model=model,
        label="openai",
    )
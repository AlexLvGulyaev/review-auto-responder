from __future__ import annotations

import logging

from config import get_settings
from providers.base import ResponseProvider
from providers.gigachat_provider import GigaChatProvider
from providers.openai_provider import OpenAICompatibleProvider
from runtime_config import get_runtime_config


logger = logging.getLogger("worker.provider.factory")


class ProviderNotConfigured(RuntimeError):
    """Провайдер не настроен (нет ключа или выключен в runtime)."""


PROVIDERS = ("openai", "gigachat")


def _is_enabled(runtime: dict, key: str) -> bool:
    return bool(runtime.get(f"{key}_enabled", True))


def build_provider_for_key(key: str) -> ResponseProvider:
    """Собрать конкретный провайдер по ключу с runtime-параметрами.

    Секреты — из .env (settings); runtime-параметры (model/base_url/
    temperature/max_tokens) — из config.json. Проверяет наличие ключа в settings
    и флаг `*_enabled` в runtime. ProviderNotConfigured — если ключ отсутствует
    или провайдер выключен.
    """
    settings = get_settings()
    runtime = get_runtime_config()

    if key == "gigachat":
        if not _is_enabled(runtime, "gigachat"):
            raise ProviderNotConfigured("GigaChat выключен в runtime")
        if not settings.gigachat_auth_key:
            raise ProviderNotConfigured("GIGACHAT_AUTH_KEY не задан")
        return GigaChatProvider(
            auth_key=settings.gigachat_auth_key,
            base_url=settings.gigachat_base_url,
            token_url=settings.gigachat_token_url,
            scope=settings.gigachat_scope,
            model=runtime.get("gigachat_model", "GigaChat-Max"),
            temperature=float(runtime.get("gigachat_temperature", 0.1)),
            max_tokens=int(runtime.get("gigachat_max_tokens", 500)),
            ca_bundle=settings.gigachat_ca_bundle,
        )

    # openai — OpenAI SDK + base_url из runtime (для OpenAI-compatible endpoint).
    if not _is_enabled(runtime, "openai"):
        raise ProviderNotConfigured("OpenAI выключен в runtime")
    if not settings.openai_api_key:
        raise ProviderNotConfigured("OPENAI_API_KEY не задан")
    return OpenAICompatibleProvider(
        api_key=settings.openai_api_key,
        base_url=runtime.get("openai_base_url", "https://api.openai.com/v1"),
        model=runtime.get("openai_model", "gpt-4.1-mini"),
        temperature=float(runtime.get("openai_temperature", 0.3)),
        max_tokens=int(runtime.get("openai_max_tokens", 1024)),
        label="openai",
    )


def _other(key: str) -> str:
    return "gigachat" if key == "openai" else "openai"


def build_active_provider() -> ResponseProvider:
    """Активный провайдер. Если не включён/нет ключа — ProviderNotConfigured
    (processor решает: fallback LLM или dict-шаблоны)."""
    runtime = get_runtime_config()
    active = runtime.get("active_provider") or runtime.get("provider") or "openai"
    return build_provider_for_key(active)


def build_fallback_provider() -> ResponseProvider | None:
    """Fallback LLM-провайдер, если он включён, сконфигурирован и отличается
    от активного. Иначе None (processor уйдёт в dict-шаблоны)."""
    runtime = get_runtime_config()
    active = runtime.get("active_provider") or runtime.get("provider") or "openai"
    fallback = runtime.get("fallback_provider") or _other(active)
    if fallback == active:
        return None
    try:
        return build_provider_for_key(fallback)
    except ProviderNotConfigured:
        return None
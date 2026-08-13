from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- целевой сайт ---
    target_site_url: str = "http://review-site:8000"
    worker_api_token: str = "change-me"
    worker_poll_interval: int = 10

    # Логирование: уровень логов (DEBUG/INFO/WARNING/ERROR), default INFO.
    log_level: str = "INFO"

    # --- локальное состояние / heartbeat ---
    state_file_path: str = "data/state.json"
    heartbeat_file_path: str = "data/heartbeat.json"

    # --- runtime-config (shared volume с сайтом; /admin пишет, worker читает) ---
    runtime_config_path: str = "/data/runtime/config.json"

    # --- идентичность AI-ответов ---
    ai_author_name: str = "AI Support"

    # --- OpenAI / OpenAI-compatible / custom ---
    openai_api_key: str = ""

    # --- GigaChat (Сбер) ---
    gigachat_auth_key: str = ""
    gigachat_base_url: str = "https://gigachat.devices.sberbank.ru/api/v1"
    gigachat_token_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_ca_bundle: str = ""

    # --- YandexGPT ---
    yandex_api_key: str = ""

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_user_chat_id: str = ""
    telegram_chat_id: str = Field(default="", deprecated=True)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
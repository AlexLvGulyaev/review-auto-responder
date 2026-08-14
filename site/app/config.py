from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_db: str = "reviews_db"
    postgres_user: str = "reviews_user"
    postgres_password: str = "reviews_password"
    postgres_host: str = "db"
    postgres_port: int = 5432
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    worker_api_token: str = "change-me"

    # Worker test-API (внутренний HTTP-сервер воркера для кнопки «Проверить»).
    # Сайт проксирует POST /admin/test-provider → http://review-worker:8001/provider-test
    # с X-Worker-Token. LLM-ключи остаются на воркере — сайт их не получает.
    worker_test_url: str = "http://review-worker:8001"

    # /admin — демо-RBAC на два токена.
    # ADMIN_TOKEN — полный доступ (мутации); ADMIN_DEMO_TOKEN — read-only.
    # admin_auth_enabled=False отключает auth (для тестов/локального режима).
    admin_token: str = "change-me"
    admin_demo_token: str = ""
    admin_auth_enabled: bool = True

    # Демо-сессии публичного сайта отзывов (токенизированный лимиттер с квотой).
    # Каждый POST /api/reviews от пользователя → воркер → LLM-генерация (расход),
    # поэтому публичная форма ограничена короткоживущими токенами с квотой.
    # demo_enabled=False отключает guard (для тестов/локального режима).
    demo_enabled: bool = True
    demo_max_requests_per_session: int = 5  # 1 POST = 1 LLM-генерация
    demo_session_ttl_minutes: int = 30
    demo_rate_limit_per_minute: int = 12  # → 5 сек между запросами
    demo_max_sessions_per_ip_per_hour: int = 5

    # Shared volume paths: /admin writes config.json here, worker hot-reloads it.
    runtime_config_path: str = "/data/runtime/config.json"
    # Промпт как файл-SOT: /admin перезаписывает этот файл, воркер читает его.
    runtime_prompt_path: str = "/data/runtime/system_prompt.md"
    # Worker status-снапшот (liveness + статус провайдеров) — сайт читает для /admin/status.
    worker_status_path: str = "/data/runtime/status.json"

    # Логирование: уровень логов (DEBUG/INFO/WARNING/ERROR), default INFO.
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
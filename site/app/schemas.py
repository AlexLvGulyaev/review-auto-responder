from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.review import ReviewStatus, ReviewTone


class ReviewCreate(BaseModel):
    parent_id: int | None = None
    name: str | None = Field(default=None, max_length=255)
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Review text cannot be empty.")
        return value


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str | None
    text: str
    status: ReviewStatus
    response: str | None
    tone: str | None
    created_at: datetime


class ReviewUpdate(BaseModel):
    status: ReviewStatus | None = None
    response: str | None = None
    tone: ReviewTone | None = None


class RuntimeConfigUpdate(BaseModel):
    """Payload of /admin — runtime parameters written to config.json.

    Secrets (API keys) are NOT here — only operator-tunable runtime params.
    The system prompt is a separate file-SOT (system_prompt.md on the shared
    volume), not a field of config.json.
    """

    provider: Literal["openai", "gigachat"] = "openai"
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    gigachat_model: str = "GigaChat-Max"


# --- Execution tracing (воркер → API сайта) -------------------------------


class ExecutionStepIn(BaseModel):
    stage_name: str = Field(min_length=1, max_length=64)
    step_order: int = Field(ge=0)
    status: Literal["ok", "error", "skipped"] = "ok"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    step_metadata: dict = Field(default_factory=dict)


class ExecutionCreate(BaseModel):
    """Старт execution-сессии (воркер вызывает POST /api/executions)."""

    review_id: int | None = None
    route: str = "review_processing"
    provider_key: str | None = None
    model_name: str | None = None
    metadata: dict = Field(default_factory=dict)


class ExecutionFinish(BaseModel):
    """Финал сессии — статус, длительность, метаданные и шаги одним пакетом."""

    status: Literal["ok", "error"]
    duration_ms: int | None = None
    provider_key: str | None = None
    model_name: str | None = None
    metadata: dict = Field(default_factory=dict)
    steps: list[ExecutionStepIn] = Field(default_factory=list)


class ExecutionStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage_name: str
    step_order: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    step_metadata: dict


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_id: int | None
    status: str
    route: str
    provider_key: str | None
    model_name: str | None
    duration_ms: int | None
    started_at: datetime
    finished_at: datetime | None
    execution_metadata: dict
    steps: list[ExecutionStepRead] = []


# --- Audit (admin/security) -----------------------------------------------


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str | None
    user_name: str | None
    user_role: str | None
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    details: dict
    created_at: datetime
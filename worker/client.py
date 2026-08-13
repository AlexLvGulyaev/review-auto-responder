import logging

import httpx

from config import get_settings
from models import RemoteReview, ReviewCreatePayload, ReviewStatus, ReviewUpdatePayload


logger = logging.getLogger("worker.client")
settings = get_settings()


class ReviewSiteClient:
    def __init__(self) -> None:
        self._base_url = settings.target_site_url.rstrip("/")
        self._headers = {"X-Worker-Token": settings.worker_api_token}

    async def check_site(self) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{self._base_url}/")
            response.raise_for_status()

    async def fetch_new_reviews(self) -> list[RemoteReview]:
        """Доработка: серверный фильтр `?status=new` — тянутся только новые отзывы,
        а не весь список с клиентской фильтрацией (как в legacy)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self._base_url}/api/reviews",
                params={"status": ReviewStatus.NEW.value},
            )
            response.raise_for_status()
        payload = response.json()
        return [RemoteReview.model_validate(item) for item in payload]

    async def create_review(self, payload: ReviewCreatePayload) -> RemoteReview:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._base_url}/api/reviews",
                json=payload.model_dump(mode="json", exclude_none=True),
            )
            response.raise_for_status()
        logger.info("Created reply review for parent id=%s", payload.parent_id)
        return RemoteReview.model_validate(response.json())

    async def update_review(self, review_id: int, payload: ReviewUpdatePayload) -> RemoteReview:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.patch(
                f"{self._base_url}/api/reviews/{review_id}",
                headers=self._headers,
                json=payload.model_dump(mode="json", exclude_none=True),
            )
            response.raise_for_status()
        logger.info("Review id=%s updated on target site", review_id)
        return RemoteReview.model_validate(response.json())

    # --- execution tracing (воркер → API сайта) ---------------------------

    async def start_execution(
        self,
        review_id: int | None,
        route: str = "review_processing",
        metadata: dict | None = None,
    ) -> int:
        """Создать execution-сессию (status=started). Возвращает session id."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._base_url}/api/executions",
                headers=self._headers,
                json={"review_id": review_id, "route": route, "metadata": metadata or {}},
            )
            response.raise_for_status()
        return int(response.json()["id"])

    async def finish_execution(
        self,
        execution_id: int,
        *,
        status: str,
        duration_ms: int | None = None,
        provider_key: str | None = None,
        model_name: str | None = None,
        metadata: dict | None = None,
        steps: list[dict] | None = None,
    ) -> None:
        """Закрыть сессию: статус, длительность, провайдер/модель, шаги."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.patch(
                f"{self._base_url}/api/executions/{execution_id}",
                headers=self._headers,
                json={
                    "status": status,
                    "duration_ms": duration_ms,
                    "provider_key": provider_key,
                    "model_name": model_name,
                    "metadata": metadata or {},
                    "steps": steps or [],
                },
            )
            response.raise_for_status()
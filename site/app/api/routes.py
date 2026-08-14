import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db_session
from app.models.demo_session import DemoSession
from app.models.review import Review, ReviewStatus
from app.api.worker_auth import require_worker_token
from app.schemas import ReviewCreate, ReviewRead, ReviewUpdate
from app.services.audit import client_ip
from app.services.demo_limiter import DemoLimiterService


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter()
settings = get_settings()


async def require_demo_or_worker(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> DemoSession | None:
    """Quota-guard публичной формы `POST /api/reviews`.

    Два пути:
    1. Воркер — доверенный внутренний вызов (создаёт AI-ответ через тот же
       эндпоинт). Валидный `X-Worker-Token` → exempt от квоты (возвращает None).
    2. Публичный демо-запрос — валидация `X-Demo-Token` и списание одного
       запроса из квоты сессии (rate-limit / quota / expiry). `demo_enabled=False`
       → guard выключен (тесты/локальный режим).

    Сессия БД общая с роутом, flush квоты коммитится вместе с insert'ом отзыва
    (атомарно: неудачная отправка не сжигает квоту — rollback на close).
    """
    # 1) Воркер — exempt.
    if settings.worker_api_token and request.headers.get("x-worker-token") == settings.worker_api_token:
        return None
    # 2) demo выключен — no-op.
    if not settings.demo_enabled:
        return None
    token = request.headers.get("x-demo-token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Demo-Token header is required. Call POST /api/demo/start.",
        )
    return await DemoLimiterService(db).check_and_record_request(token, client_ip(request))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/health")
async def health() -> dict[str, str]:
    """Health-эндпоинт для Deployment Validation и Docker healthcheck."""
    return {"status": "ok"}


@router.get("/api/reviews", response_model=list[ReviewRead])
async def list_reviews(
    status_filter: ReviewStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db_session),
) -> list[Review]:
    """Список отзывов. Опциональный серверный фильтр `?status=new`/`?status=processed`.

    Доработка относительно legacy: фильтрация на стороне БД, а не клиентский
    фильтр по полному списку — обработчик тянет только новые отзывы.
    Параметр exposed как `?status=...` (alias), переменная — `status_filter`
    (не затеняет fastapi.status).
    """
    stmt = select(Review)
    if status_filter is not None:
        stmt = stmt.where(Review.status == status_filter)
    stmt = stmt.order_by(Review.created_at.desc(), Review.id.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/api/reviews", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
async def create_review(
    request: Request,
    response: Response,
    payload: ReviewCreate,
    session: AsyncSession = Depends(get_db_session),
    demo_session: DemoSession | None = Depends(require_demo_or_worker),
) -> Review:
    if not payload.text.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Review text is required.")

    if payload.parent_id is not None:
        parent_review = await session.get(Review, payload.parent_id)
        if parent_review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent review not found.")

    review = Review(
        parent_id=payload.parent_id,
        name=payload.name,
        text=payload.text,
        status=ReviewStatus.NEW,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    # UI-бейдж квоты: оставшиеся запросы в демо-сессии (воркеру не нужно).
    if demo_session is not None:
        response.headers["X-Demo-Remaining"] = str(
            max(0, demo_session.requests_limit - demo_session.requests_used)
        )
    logger.info(
        "review.create id=%s parent=%s author=%r len=%d ip=%s demo=%s",
        review.id,
        review.parent_id,
        review.name,
        len(review.text),
        request.client.host if request.client else None,
        demo_session is not None,
    )
    return review


@router.patch("/api/reviews/{review_id}", response_model=ReviewRead)
async def update_review(
    review_id: int,
    payload: ReviewUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _token: str = Depends(require_worker_token),
) -> Review:
    review = await session.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")

    if payload.status is not None:
        review.status = payload.status
    if payload.response is not None:
        review.response = payload.response
    if payload.tone is not None:
        review.tone = payload.tone.value

    await session.commit()
    await session.refresh(review)
    logger.info(
        "review.update id=%s status=%s tone=%s",
        review.id,
        review.status,
        review.tone,
    )
    return review
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.review import Review, ReviewStatus
from app.api.worker_auth import require_worker_token
from app.schemas import ReviewCreate, ReviewRead, ReviewUpdate


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
router = APIRouter()


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
    payload: ReviewCreate,
    session: AsyncSession = Depends(get_db_session),
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
    logger.info(
        "review.create id=%s parent=%s author=%r len=%d ip=%s",
        review.id,
        review.parent_id,
        review.name,
        len(review.text),
        request.client.host if request.client else None,
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
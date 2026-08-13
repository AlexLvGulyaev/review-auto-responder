import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.admin import router as admin_router
from app.api.admin_executions import router as admin_executions_router
from app.api.admin_status import router as admin_status_router
from app.api.audit import router as audit_router
from app.api.executions import router as executions_router
from app.api.routes import router as reviews_router
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine
from app.models import Review  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.execution import ExecutionSession, ExecutionStep  # noqa: F401


configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Initializing database schema")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # Idempotent add columns for legacy DBs (tone, parent_id).
        await connection.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS tone VARCHAR(32)"))
        await connection.execute(text("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS parent_id INTEGER"))
    yield


app = FastAPI(title="Reviews App", lifespan=lifespan)
app.include_router(reviews_router)
app.include_router(admin_router)
app.include_router(executions_router)
app.include_router(audit_router)
app.include_router(admin_executions_router)
app.include_router(admin_status_router)
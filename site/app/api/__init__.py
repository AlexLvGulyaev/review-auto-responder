from app.api.admin import router as admin_router
from app.api.routes import router as reviews_router

__all__ = ["admin_router", "reviews_router"]
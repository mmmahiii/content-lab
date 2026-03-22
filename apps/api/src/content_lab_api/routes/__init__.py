"""API route definitions."""

from fastapi import APIRouter

from content_lab_api.routes.health import router as health_router
from content_lab_api.routes.pages import router as pages_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(pages_router)

__all__ = ["api_router"]

"""API route definitions."""

from fastapi import APIRouter

from content_lab_api.routes.health import router as health_router
from content_lab_api.routes.pages import router as pages_router
from content_lab_api.routes.reel_families import router as reel_families_router
from content_lab_api.routes.reels import router as reels_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(pages_router)
api_router.include_router(reel_families_router)
api_router.include_router(reels_router)

__all__ = ["api_router"]

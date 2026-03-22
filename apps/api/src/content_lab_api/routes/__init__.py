"""API route definitions."""

from fastapi import APIRouter

from content_lab_api.routes.assets import router as assets_router
from content_lab_api.routes.health import router as health_router
from content_lab_api.routes.pages import router as pages_router
from content_lab_api.routes.policy import router as policy_router
from content_lab_api.routes.reel_families import router as reel_families_router
from content_lab_api.routes.reels import router as reels_router
from content_lab_api.routes.runs import router as runs_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(assets_router)
api_router.include_router(pages_router)
api_router.include_router(policy_router)
api_router.include_router(reel_families_router)
api_router.include_router(reels_router)
api_router.include_router(runs_router)

__all__ = ["api_router"]

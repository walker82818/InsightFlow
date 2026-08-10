"""API v1 package."""
from fastapi import APIRouter

from app.api.v1 import analyses, datasets

api_router = APIRouter()
api_router.include_router(datasets.router)
api_router.include_router(analyses.router)

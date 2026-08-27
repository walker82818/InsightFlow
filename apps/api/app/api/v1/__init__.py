"""API v1 package."""
from fastapi import APIRouter

from app.api.v1 import analyses, datasets, evaluations, evals_replay

api_router = APIRouter()
api_router.include_router(datasets.router)
api_router.include_router(analyses.router)
api_router.include_router(evaluations.router)
api_router.include_router(evals_replay.router)

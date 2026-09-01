"""Shared FastAPI dependency: resolve the single fixed local user."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.user import User


async def get_current_user(
    session: AsyncSession = Depends(get_session),
) -> User:
    """Open-source single-user mode: always operate as the fixed default user.

    A persisted row may not exist yet on a fresh DB, so we synthesize a
    lightweight User object — no registration or login required.
    """
    user = await session.get(User, settings.default_user_id)
    if user is not None:
        return user
    return User(
        id=settings.default_user_id,
        username="local",
        hashed_password="",
        created_at=datetime.now(timezone.utc),
    )

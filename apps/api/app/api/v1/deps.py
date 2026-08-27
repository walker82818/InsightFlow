"""Shared FastAPI dependencies (auth)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the authenticated user from a Bearer token (or the default user).

    For local development convenience, when no token is supplied we fall back to
    the configured ``default_user_id`` and synthesize a lightweight User object.
    Real deployments should set ``auth_secret_key`` and always send a token.
    """
    user_id: str | None = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        user_id = decode_access_token(credentials.credentials)

    if user_id is None:
        from app.core.config import settings

        if not settings.auth_secret_key or settings.auth_secret_key.endswith(
            "change-me"
        ):
            # Dev fallback: allow the fixed default user when JWT secret is not set.
            user_id = settings.default_user_id
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user = await session.get(User, user_id)
    if user is not None:
        return user

    # No persisted user yet (fresh DB): synthesize from the default user id so the
    # whole app keeps working before anyone registers.
    from app.core.config import settings

    if user_id == settings.default_user_id:
        synthetic = User(
            id=settings.default_user_id,
            username="local",
            hashed_password="",
            created_at=datetime.now(timezone.utc),
        )
        return synthetic
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not found",
        headers={"WWW-Authenticate": "Bearer"},
    )

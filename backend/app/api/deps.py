"""Reusable FastAPI dependencies."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuthSession, User
from app.db.session import get_db
from app.services.auth.security import hash_session_token


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )

    token_hash = hash_session_token(token)
    auth_session = db.scalar(
        select(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .where(AuthSession.expires_at > datetime.now(UTC))
    )
    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    return auth_session.user


CurrentUser = Annotated[User, Depends(get_current_user)]

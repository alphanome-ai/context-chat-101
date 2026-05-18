from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.db.models import User
from app.services.auth.security import (
    create_jwt_token,
    hash_password,
    normalize_email,
    verify_password,
)

router = APIRouter()


class AuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    token: str
    expires_at: datetime
    user: UserResponse


def _create_auth_response(user: User) -> AuthResponse:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(days=settings.auth_session_days)
    token = create_jwt_token(
        user_id=user.id,
        expires_at=expires_at,
        secret=settings.auth_jwt_secret,
    )
    return AuthResponse(
        token=token,
        expires_at=expires_at,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: AuthRequest, db: DbSession) -> AuthResponse:
    email = normalize_email(payload.email)
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _create_auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthRequest, db: DbSession) -> AuthResponse:
    email = normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return _create_auth_response(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> User:
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(_current_user: CurrentUser) -> None:
    return None

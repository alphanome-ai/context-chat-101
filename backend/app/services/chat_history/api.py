from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.db.models import ChatMessage, ChatSession, utc_now

router = APIRouter()


class ChatMessageCreate(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    thinking: str | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=120)
    messages: list[ChatMessageCreate] = Field(default_factory=list)


class ChatMessagesCreate(BaseModel):
    messages: list[ChatMessageCreate] = Field(min_length=1)
    model: str | None = Field(default=None, max_length=120)


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    thinking: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    position: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionSummary(BaseModel):
    id: int
    title: str
    model: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int


class ChatSessionResponse(BaseModel):
    id: int
    title: str
    model: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]

    model_config = ConfigDict(from_attributes=True)


def _make_title(messages: list[ChatMessageCreate], fallback: str | None) -> str:
    if fallback and fallback.strip():
        return fallback.strip()[:160]

    first_user_message = next((message.content for message in messages if message.role == "user"), "")
    title = " ".join(first_user_message.split())
    if not title:
        return "New chat"
    return title[:80]


def _get_user_session(db: DbSession, user_id: int, session_id: int) -> ChatSession:
    chat_session = db.scalar(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id)
        .where(ChatSession.user_id == user_id)
    )
    if chat_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return chat_session


def _append_messages(
    db: DbSession,
    chat_session: ChatSession,
    messages: list[ChatMessageCreate],
) -> None:
    max_position = db.scalar(
        select(func.max(ChatMessage.position)).where(ChatMessage.session_id == chat_session.id)
    )
    next_position = max_position + 1 if max_position is not None else 0

    for offset, message in enumerate(messages):
        db.add(
            ChatMessage(
                session_id=chat_session.id,
                role=message.role,
                content=message.content,
                thinking=message.thinking.strip() if message.thinking else None,
                prompt_tokens=message.prompt_tokens,
                completion_tokens=message.completion_tokens,
                total_tokens=message.total_tokens,
                position=next_position + offset,
            )
        )

    chat_session.updated_at = utc_now()


@router.get("", response_model=list[ChatSessionSummary])
def list_chat_sessions(current_user: CurrentUser, db: DbSession) -> list[ChatSessionSummary]:
    rows = db.execute(
        select(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage)
        .where(ChatSession.user_id == current_user.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    ).all()

    return [
        ChatSessionSummary(
            id=chat_session.id,
            title=chat_session.title,
            model=chat_session.model,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
            message_count=message_count,
        )
        for chat_session, message_count in rows
    ]


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_chat_session(
    payload: ChatSessionCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ChatSession:
    chat_session = ChatSession(
        user_id=current_user.id,
        title=_make_title(payload.messages, payload.title),
        model=payload.model,
    )
    db.add(chat_session)
    db.flush()

    if payload.messages:
        _append_messages(db, chat_session, payload.messages)

    db.commit()
    return _get_user_session(db, current_user.id, chat_session.id)


@router.get("/{session_id}", response_model=ChatSessionResponse)
def get_chat_session(session_id: int, current_user: CurrentUser, db: DbSession) -> ChatSession:
    return _get_user_session(db, current_user.id, session_id)


@router.post("/{session_id}/messages", response_model=ChatSessionResponse)
def add_chat_messages(
    session_id: int,
    payload: ChatMessagesCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ChatSession:
    chat_session = _get_user_session(db, current_user.id, session_id)
    if payload.model:
        chat_session.model = payload.model
    _append_messages(db, chat_session, payload.messages)
    db.commit()
    return _get_user_session(db, current_user.id, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_session(session_id: int, current_user: CurrentUser, db: DbSession) -> Response:
    chat_session = _get_user_session(db, current_user.id, session_id)
    db.delete(chat_session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

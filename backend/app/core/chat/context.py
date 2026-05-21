from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.chat.errors import ChatContextError
from app.core.llm.schemas import ChatMessage
from app.db.models import ChatMessage as StoredChatMessage
from app.db.models import ChatSession


class ChatContextManager:
    def __init__(self, db: Session) -> None:
        self._db = db

    def build_messages(
        self,
        *,
        user_id: str,
        session_id: str | None,
        user_message: str,
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = []

        if session_id is not None:
            chat_session = self._load_session(user_id=user_id, session_id=session_id)
            if chat_session.mode != "chat":
                raise ChatContextError(
                    "This session is not a chat-mode session.",
                    status_code=400,
                    error_code="INVALID_CHAT_SESSION_MODE",
                )

            messages.extend(
                context_message
                for message in chat_session.messages
                if (context_message := _to_context_message(message)) is not None
            )

        messages.append(ChatMessage(role="user", content=user_message))
        return messages

    def _load_session(self, *, user_id: str, session_id: str) -> ChatSession:
        chat_session = self._db.scalar(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == session_id)
            .where(ChatSession.user_id == user_id)
        )
        if chat_session is None:
            raise ChatContextError(
                "Chat session not found.",
                status_code=404,
                error_code="CHAT_SESSION_NOT_FOUND",
            )
        return chat_session


def _to_context_message(message: StoredChatMessage) -> ChatMessage | None:
    if message.role == "user":
        return ChatMessage(role="user", content=message.content)
    if message.role == "assistant":
        return ChatMessage(role="assistant", content=message.content)
    return None

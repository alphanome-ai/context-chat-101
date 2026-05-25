import time

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.logging import get_app_logger
from app.core.llm.schemas import ChatMessage
from app.db.models import ChatMessage as StoredChatMessage
from app.db.models import ChatSession

logger = get_app_logger()


class ChatContextError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, error_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class ChatContextManager:
    def __init__(self, db: Session) -> None:
        self._db = db

    def build_messages(
        self,
        *,
        user_id: str,
        session_id: str | None,
        user_message: str,
        session_mode: str = "chat",
    ) -> list[ChatMessage]:
        started_at = time.perf_counter()
        messages: list[ChatMessage] = []
        persisted_message_count = 0
        status = "ok"

        try:
            if session_id is not None:
                chat_session = self._load_session(user_id=user_id, session_id=session_id)
                if chat_session.mode != session_mode:
                    raise ChatContextError(
                        f"This session is not a {session_mode}-mode session.",
                        status_code=400,
                        error_code="INVALID_CHAT_SESSION_MODE",
                    )

                messages.extend(
                    context_message
                    for message in chat_session.messages
                    if (context_message := _to_context_message(message)) is not None
                )
                persisted_message_count = len(messages)

            messages.append(ChatMessage(role="user", content=user_message))
            return messages
        except ChatContextError as exc:
            status = exc.error_code
            raise
        except Exception:
            status = "unexpected_error"
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.debug(
                (
                    "chat_context_build status={} session_id={} persisted_messages={} "
                    "output_messages={} elapsed_ms={:.2f}"
                ),
                status,
                session_id or "-",
                persisted_message_count,
                len(messages),
                elapsed_ms,
            )

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

import os
import tempfile
import time
from collections.abc import Callable, Sequence
from typing import Any

from app.core.config import Settings
from app.core.llm.schemas import ChatMessage
from app.core.logging import get_app_logger
from app.core.services.context import ChatContextManager

os.environ.setdefault("MEM0_DIR", os.path.join(tempfile.gettempdir(), "context-chat-mem0"))

from mem0 import MemoryClient  # noqa: E402

logger = get_app_logger()

MEM0_AGENT_ID = "agent0"


class Mem0ContextChatManager:
    def __init__(
        self,
        context_manager: ChatContextManager,
        *,
        settings: Settings,
        memory_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._settings = settings
        self._memory_client_factory = memory_client_factory or self._create_memory_client
        self._memory_client: Any | None = None

    def build_messages(
        self,
        *,
        user_id: str,
        session_id: str | None,
        user_message: str,
        session_mode: str = "agent0",
    ) -> list[ChatMessage]:
        messages = self._context_manager.build_messages(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            session_mode=session_mode,
        )
        memories = self._search_memories(user_id=user_id, user_message=user_message)
        if not memories:
            return messages

        return [
            ChatMessage(role="system", content=_format_memory_context(memories)),
            *messages,
        ]

    def remember_exchange(
        self,
        *,
        user_id: str,
        session_id: str | None,
        user_message: str,
        assistant_message: str,
    ) -> None:
        if not self._settings.mem0_api_key or not assistant_message:
            return

        started_at = time.perf_counter()
        status = "ok"
        try:
            self._client.add(
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_message},
                ],
                user_id=user_id,
                agent_id=MEM0_AGENT_ID,
                run_id=session_id,
                metadata={"session_id": session_id} if session_id else None,
            )
        except Exception:
            status = "unexpected_error"
            logger.warning("mem0_memory_add_failed user_id={} session_id={}", user_id, session_id or "-")
            raise
        finally:
            elapsed_s = time.perf_counter() - started_at
            logger.debug(
                "mem0_memory_add status={} user_id={} session_id={} elapsed_s={:.3f}",
                status,
                user_id,
                session_id or "-",
                elapsed_s,
            )

    def _search_memories(self, *, user_id: str, user_message: str) -> list[str]:
        if not self._settings.mem0_api_key:
            return []

        started_at = time.perf_counter()
        status = "ok"
        memories: list[str] = []
        try:
            response = self._client.search(
                user_message,
                filters={"user_id": user_id},
                top_k=self._settings.mem0_top_k,
            )
            memories = _extract_memories(response)
            return memories
        except Exception:
            status = "unexpected_error"
            logger.warning(
                "mem0_memory_search_failed user_id={} query={!r}",
                user_id,
                user_message,
            )
            raise
        finally:
            elapsed_s = time.perf_counter() - started_at
            logger.debug(
                (
                    "mem0_memory_search status={} user_id={} query={!r} "
                    "memory_count={} memories={} elapsed_s={:.3f}"
                ),
                status,
                user_id,
                user_message,
                len(memories),
                memories,
                elapsed_s,
            )

    @property
    def _client(self) -> Any:
        if self._memory_client is None:
            self._memory_client = self._memory_client_factory()
        return self._memory_client

    def _create_memory_client(self) -> MemoryClient:
        return MemoryClient(api_key=self._settings.mem0_api_key)


def _format_memory_context(memories: Sequence[str]) -> str:
    formatted_memories = "\n".join(f"- {memory}" for memory in memories)
    return (
        "Relevant long-term memories for this user:\n"
        f"{formatted_memories}\n\n"
        "Use these memories only when they are relevant to the current request."
    )


def _extract_memories(response: Any) -> list[str]:
    if not isinstance(response, dict):
        return []

    results = response.get("results")
    if not isinstance(results, list):
        return []

    memories: list[str] = []
    for item in results:
        memory = _extract_memory_text(item)
        if memory:
            memories.append(memory)
    return memories


def _extract_memory_text(item: Any) -> str | None:
    if isinstance(item, str):
        return item.strip() or None
    if not isinstance(item, dict):
        return None

    for key in ("memory", "text", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("memory")
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None

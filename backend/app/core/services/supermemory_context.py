import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.core.llm.schemas import ChatMessage
from app.core.logging import get_app_logger
from app.core.services.context import ChatContextManager

logger = get_app_logger()


@dataclass(frozen=True)
class SupermemoryUserContext:
    static: tuple[str, ...] = ()
    dynamic: tuple[str, ...] = ()
    memories: tuple[str, ...] = ()

    @property
    def has_context(self) -> bool:
        return bool(self.static or self.dynamic or self.memories)


class SupermemoryContextChatManager:
    def __init__(
        self,
        context_manager: ChatContextManager,
        *,
        settings: Settings,
        memory_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._settings = settings
        self._memory_client_factory = (
            memory_client_factory or self._create_memory_client
        )
        self._memory_client: Any | None = None

    def build_messages(
        self,
        *,
        user_id: str,
        session_id: str | None,
        user_message: str,
        session_mode: str = "agent1",
    ) -> list[ChatMessage]:
        self._context_manager.validate_session(
            user_id=user_id,
            session_id=session_id,
            session_mode=session_mode,
        )
        messages = [ChatMessage(role="user", content=user_message)]
        user_context = self._load_user_context(
            user_id=user_id, user_message=user_message
        )
        if not user_context.has_context:
            return messages

        return [
            ChatMessage(role="system", content=_format_user_context(user_context)),
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
        if not self._settings.supermemory_api_key or not assistant_message:
            return

        started_at = time.perf_counter()
        status = "ok"
        try:
            self._add_memory(
                content=_format_exchange_memory(
                    user_message=user_message,
                    assistant_message=assistant_message,
                ),
                user_id=user_id,
                metadata={"session_id": session_id} if session_id else None,
            )
        except Exception:
            status = "unexpected_error"
            logger.warning(
                "supermemory_memory_add_failed user_id={} session_id={}",
                user_id,
                session_id or "-",
            )
            raise
        finally:
            elapsed_s = time.perf_counter() - started_at
            logger.debug(
                (
                    "supermemory_memory_add status={} user_id={} session_id={} "
                    "elapsed_s={:.3f}"
                ),
                status,
                user_id,
                session_id or "-",
                elapsed_s,
            )

    def _load_user_context(
        self, *, user_id: str, user_message: str
    ) -> SupermemoryUserContext:
        if not self._settings.supermemory_api_key:
            return SupermemoryUserContext()

        try:
            started_at = time.perf_counter()
            response = self._profile(user_id=user_id, query=user_message)
            elapsed_s = time.perf_counter() - started_at
            logger.debug(
                (
                    "supermemory_memory_profile_response user_id={} response={} "
                    "elapsed_s={:.3f}"
                ),
                user_id,
                response,
                elapsed_s,
            )
            return _extract_user_context(response)
        except Exception as exc:
            logger.warning(
                "supermemory_memory_profile_failed user_id={} query={!r} error={}",
                user_id,
                user_message,
                str(exc),
            )
            raise

    def _profile(self, *, user_id: str, query: str) -> Any:
        kwargs: dict[str, Any] = {
            "container_tag": user_id,
            "q": query,
        }
        if self._settings.supermemory_profile_threshold is not None:
            kwargs["threshold"] = self._settings.supermemory_profile_threshold

        try:
            # logger.debug(
            #     "supermemory_profile_request user_id={} query={!r} kwargs={}",
            #     user_id,
            #     query,
            #     kwargs,
            # )
            return self._client.profile(**kwargs)
        except TypeError:
            kwargs["containerTag"] = kwargs.pop("container_tag")
            return self._client.profile(**kwargs)

    def _add_memory(
        self,
        *,
        content: str,
        user_id: str,
        metadata: dict[str, str | None] | None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "content": content,
            "container_tag": user_id,
        }
        if metadata:
            kwargs["metadata"] = metadata

        try:
            return self._client.add(**kwargs)
        except TypeError:
            payload: dict[str, Any] = {
                "content": content,
                "containerTag": user_id,
            }
            if metadata:
                payload["metadata"] = metadata
            return self._client.add(payload)

    @property
    def _client(self) -> Any:
        if self._memory_client is None:
            self._memory_client = self._memory_client_factory()
        return self._memory_client

    def _create_memory_client(self) -> Any:
        from supermemory import Supermemory

        return Supermemory(api_key=self._settings.supermemory_api_key)


def _format_user_context(user_context: SupermemoryUserContext) -> str:
    return (
        "User context from Supermemory:\n\n"
        "Static profile:\n"
        f"{_format_section(user_context.static)}\n\n"
        "Dynamic profile:\n"
        f"{_format_section(user_context.dynamic)}\n\n"
        "Relevant memories:\n"
        f"{_format_section(user_context.memories)}\n\n"
        "Use these memories only when they are relevant to the current request."
    )


def _format_section(items: Sequence[str]) -> str:
    if not items:
        return "None"
    return "\n".join(items)


def _format_exchange_memory(*, user_message: str, assistant_message: str) -> str:
    return f"User: {user_message}\nAssistant: {assistant_message}"


def _extract_user_context(response: Any) -> SupermemoryUserContext:
    if response is None:
        return SupermemoryUserContext()
    if isinstance(response, str):
        stripped = response.strip()
        return (
            SupermemoryUserContext(memories=(stripped,))
            if stripped
            else SupermemoryUserContext()
        )
    if isinstance(response, list | tuple):
        return SupermemoryUserContext(memories=_extract_memory_items(response))
    if hasattr(response, "model_dump"):
        response = response.model_dump()
    elif hasattr(response, "to_dict"):
        response = response.to_dict()

    if not isinstance(response, dict):
        return SupermemoryUserContext()

    static: tuple[str, ...] = ()
    dynamic: tuple[str, ...] = ()
    memories: tuple[str, ...] = ()

    profile = response.get("profile")
    if isinstance(profile, dict):
        static = _extract_text_items(profile.get("static"))
        dynamic = _extract_text_items(profile.get("dynamic"))
    elif isinstance(profile, str) and profile.strip():
        static = (profile.strip(),)
    else:
        static = _extract_text_items(response.get("static"))
        dynamic = _extract_text_items(response.get("dynamic"))

    search_results = response.get("search_results")
    if isinstance(search_results, dict):
        results = search_results.get("results")
        if isinstance(results, list):
            memories = _extract_memory_items(results)

    if not memories:
        for key in ("memories", "results", "facts", "items"):
            value = response.get(key)
            if isinstance(value, list):
                memories = _extract_memory_items(value)
                break

    if static or dynamic or memories:
        return SupermemoryUserContext(
            static=static,
            dynamic=dynamic,
            memories=memories,
        )

    for key in ("context", "summary"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return SupermemoryUserContext(memories=(value.strip(),))

    return SupermemoryUserContext()


def _extract_text_items(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, list | tuple):
        return tuple(
            item.strip() for item in value if isinstance(item, str) and item.strip()
        )
    return ()


def _extract_memory_items(items: Sequence[Any]) -> tuple[str, ...]:
    return tuple(
        memory for item in items if (memory := _extract_memory_text(item)) is not None
    )


def _extract_memory_text(item: Any) -> str | None:
    if isinstance(item, str):
        return item.strip() or None
    if hasattr(item, "model_dump"):
        item = item.model_dump()
    elif hasattr(item, "to_dict"):
        item = item.to_dict()
    if not isinstance(item, dict):
        return None

    for key in ("memory", "text", "content", "summary", "profile"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        for key in ("memory", "text", "content"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return None

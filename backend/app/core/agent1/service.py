from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import openai
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.llm.schemas import ChatMessage
from app.core.logging import get_app_logger
from app.core.services.context import ChatContextManager
from app.core.services.supermemory_context import SupermemoryContextChatManager

logger = get_app_logger()

Agent1EventType = Literal[
    "agent_started",
    "tool_started",
    "tool_completed",
    "tool_failed",
    "recovery_started",
    "recovery_completed",
    "message_delta",
    "agent_completed",
    "error",
]


class Agent1RunRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    model: str | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message cannot be empty")
        return stripped

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError("session_id must be a UUID") from exc
        return value


class Agent1Event(BaseModel):
    type: Agent1EventType
    message: str | None = None
    tool_name: str | None = None
    payload: dict[str, Any] | list[Any] | str | None = None


class Agent1Error(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        status_code: int = 500,
        raw: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.raw = raw


@dataclass(frozen=True)
class Agent1ModelConfig:
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class Agent1ModelFactory:
    settings: Settings

    def primary(self) -> Any:
        return self._chat_model(
            Agent1ModelConfig(
                base_url=self.settings.agent1_llm_base_url,
                api_key=self.settings.agent1_llm_api_key,
                model=self.settings.agent1_model,
            )
        )

    def recovery(self) -> Any:
        return self._chat_model(
            Agent1ModelConfig(
                base_url=self.settings.agent1_recovery_llm_base_url,
                api_key=self.settings.agent1_recovery_llm_api_key,
                model=self.settings.agent1_recovery_model,
            )
        )

    def _chat_model(self, config: Agent1ModelConfig) -> Any:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "api_key": config.api_key,
            "model": config.model,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatOpenAI(**kwargs)


AgentFactory = Callable[[Any, list[Any], str], Any]
EmitEvent = Callable[[Agent1Event], Awaitable[None]]
SearchToolFactory = Callable[[list[dict[str, Any]], EmitEvent], Any]


class Agent1Service:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        model_factory: Agent1ModelFactory | None = None,
        agent_factory: AgentFactory | None = None,
        search_tool_factory: SearchToolFactory | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model_factory = model_factory or Agent1ModelFactory(self.settings)
        self.agent_factory = agent_factory or self._create_agent
        self.search_tool_factory = search_tool_factory or self._create_search_tool

    def validate_configuration(self) -> None:
        missing = [
            name
            for name, value in {
                "AGENT1_LLM_API_KEY": self.settings.agent1_llm_api_key,
                "AGENT1_MODEL": self.settings.agent1_model,
                "AGENT1_RECOVERY_LLM_API_KEY": self.settings.agent1_recovery_llm_api_key,
                "AGENT1_RECOVERY_MODEL": self.settings.agent1_recovery_model,
                "TAVILY_API_KEY": self.settings.tavily_api_key,
                "SUPERMEMORY_API_KEY": self.settings.supermemory_api_key,
            }.items()
            if not value
        ]
        if missing:
            raise Agent1Error(
                f"Agent1 is missing required configuration: {', '.join(missing)}",
                error_code="AGENT1_CONFIGURATION_ERROR",
                status_code=503,
            )

    def stream(
        self,
        request: Agent1RunRequest,
        *,
        db: Session,
        user_id: str,
    ) -> AsyncIterator[Agent1Event]:
        context_manager = SupermemoryContextChatManager(
            ChatContextManager(db),
            settings=self.settings,
        )
        messages = context_manager.build_messages(
            user_id=user_id,
            session_id=request.session_id,
            user_message=request.message,
            session_mode="agent1",
        )

        async def _iterator() -> AsyncIterator[Agent1Event]:
            queue: asyncio.Queue[Agent1Event | None] = asyncio.Queue()
            task = asyncio.create_task(
                self._run(
                    messages,
                    queue.put,
                    context_manager=context_manager,
                    user_id=user_id,
                    session_id=request.session_id,
                    user_message=request.message,
                )
            )

            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                    yield event
                await task
            except asyncio.CancelledError:
                task.cancel()
                raise

        return _iterator()

    async def _run(
        self,
        messages: Sequence[ChatMessage],
        emit: Callable[[Agent1Event | None], Awaitable[None]],
        *,
        context_manager: SupermemoryContextChatManager,
        user_id: str,
        session_id: str | None,
        user_message: str,
    ) -> None:
        completed_tool_results: list[dict[str, Any]] = []
        recovered = False

        async def emit_event(event: Agent1Event) -> None:
            await emit(event)

        try:
            await emit_event(
                Agent1Event(type="agent_started", message="Agent1 started.")
            )
            logger.success(f"Agent1 running with messages: {messages}")
            final_answer = await self._run_primary_agent(
                messages,
                completed_tool_results=completed_tool_results,
                emit=emit_event,
            )
        except Exception as exc:
            if not _is_recoverable_model_error(exc):
                await emit_event(
                    Agent1Event(
                        type="error",
                        message=str(exc),
                        payload={"code": _error_code(exc)},
                    )
                )
                await emit(None)
                return

            try:
                logger.success(f"Agent1 (recovery) running with messages: {messages}")
                final_answer = await self._run_recovery(
                    messages,
                    completed_tool_results=completed_tool_results,
                    failure=exc,
                    emit=emit_event,
                )
                recovered = True
            except Exception as recovery_exc:
                await emit_event(
                    Agent1Event(
                        type="error",
                        message=str(recovery_exc),
                        payload={"code": _error_code(recovery_exc), "recovery": True},
                    )
                )
                await emit(None)
                return

        if final_answer:
            await emit_event(Agent1Event(type="message_delta", message=final_answer))
            try:
                await asyncio.to_thread(
                    context_manager.remember_exchange,
                    user_id=user_id,
                    session_id=session_id,
                    user_message=user_message,
                    assistant_message=final_answer,
                )
            except Exception:
                pass
        await emit_event(
            Agent1Event(
                type="agent_completed",
                message="Agent1 completed.",
                payload={"recovered": recovered},
            )
        )
        await emit(None)

    async def _run_primary_agent(
        self,
        messages: Sequence[ChatMessage],
        *,
        completed_tool_results: list[dict[str, Any]],
        emit: EmitEvent,
    ) -> str:
        model = self.model_factory.primary()
        tools = [self.search_tool_factory(completed_tool_results, emit)]
        agent = self.agent_factory(model, tools, AGENT1_SYSTEM_PROMPT)
        result = await agent.ainvoke({"messages": _langchain_messages(messages)})
        return _extract_text(result)

    async def _run_recovery(
        self,
        messages: Sequence[ChatMessage],
        *,
        completed_tool_results: list[dict[str, Any]],
        failure: Exception,
        emit: EmitEvent,
    ) -> str:
        await emit(
            Agent1Event(
                type="recovery_started",
                message="Primary model failed; recovery model started.",
                payload={"error": str(failure), "code": _error_code(failure)},
            )
        )
        model = self.model_factory.recovery()
        recovery_messages = [
            {
                "role": "system",
                "content": AGENT1_RECOVERY_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": _recovery_prompt(messages, completed_tool_results),
            },
        ]
        result = await model.ainvoke(recovery_messages)
        final_answer = _extract_text(result)
        await emit(
            Agent1Event(
                type="recovery_completed",
                message="Recovery model completed.",
                payload={"code": _error_code(failure)},
            )
        )
        return final_answer

    def _create_agent(self, model: Any, tools: list[Any], system_prompt: str) -> Any:
        from deepagents import create_deep_agent

        return create_deep_agent(model=model, tools=tools, system_prompt=system_prompt)

    def _create_search_tool(
        self,
        completed_tool_results: list[dict[str, Any]],
        emit: EmitEvent,
    ) -> Any:
        from langchain_core.tools import tool
        from langchain_tavily import TavilySearch

        os.environ["TAVILY_API_KEY"] = self.settings.tavily_api_key
        tavily_search = TavilySearch(
            max_results=5,
            topic="general",
            search_depth="basic",
            include_answer=False,
            include_raw_content=False,
            include_images=False,
        )

        @tool("web_search")
        async def web_search(query: str) -> str:
            """Search the web for current public information."""

            await emit(
                Agent1Event(
                    type="tool_started",
                    message=f"Searching for {query}",
                    tool_name="web_search",
                    payload={"query": query},
                )
            )
            try:
                result = await tavily_search.ainvoke({"query": query})
            except Exception as exc:
                await emit(
                    Agent1Event(
                        type="tool_failed",
                        message=str(exc),
                        tool_name="web_search",
                        payload={"query": query, "code": _error_code(exc)},
                    )
                )
                raise

            payload = _compact_search_result(result)
            completed_tool_results.append({"query": query, "result": payload})
            await emit(
                Agent1Event(
                    type="tool_completed",
                    message=f"Search completed for {query}",
                    tool_name="web_search",
                    payload=payload,
                )
            )
            return json.dumps(payload, ensure_ascii=False)

        return web_search


AGENT1_SYSTEM_PROMPT = (
    "You are Agent1, a concise web research agent with Supermemory-backed long-term "
    "context. Use web_search for current or externally verifiable information. Cite "
    "source URLs in the answer when search results are used. Do not mention internal "
    "tool events."
)

AGENT1_RECOVERY_SYSTEM_PROMPT = (
    "You are Agent1's recovery model. Produce the best final answer from the user "
    "request, conversation context, and any completed tool results. Do not call tools. "
    "Do not mention recovery unless the user asks."
)


def _langchain_messages(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    return [
        {
            "role": message.role,
            "content": message.content if isinstance(message.content, str) else "",
        }
        for message in messages
        if message.role in {"system", "user", "assistant"}
    ]


def _recovery_prompt(
    messages: Sequence[ChatMessage],
    completed_tool_results: Sequence[dict[str, Any]],
) -> str:
    conversation = "\n".join(
        f"{message.role}: {message.content}"
        for message in messages
        if isinstance(message.content, str)
    )
    tool_results = json.dumps(completed_tool_results, ensure_ascii=False, indent=2)
    return (
        "Conversation:\n"
        f"{conversation}\n\n"
        "Completed tool results:\n"
        f"{tool_results or '[]'}"
    )


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        if (
            "messages" in value
            and isinstance(value["messages"], list)
            and value["messages"]
        ):
            return _extract_text(value["messages"][-1])
        content = value.get("content")
        return _content_to_text(content).strip()

    content = getattr(value, "content", None)
    return _content_to_text(content).strip()


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return "" if content is None else str(content)


def _compact_search_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    if not isinstance(result, dict):
        return {"raw": str(result)}

    compact: dict[str, Any] = {}
    if query := result.get("query"):
        compact["query"] = query
    results = result.get("results")
    if isinstance(results, list):
        compact["results"] = [
            {
                key: value
                for key, value in {
                    "title": item.get("title") if isinstance(item, dict) else None,
                    "url": item.get("url") if isinstance(item, dict) else None,
                    "content": item.get("content") if isinstance(item, dict) else None,
                    "score": item.get("score") if isinstance(item, dict) else None,
                }.items()
                if value is not None
            }
            for item in results[:5]
            if isinstance(item, dict)
        ]
    return compact or result


def _is_recoverable_model_error(exc: Exception) -> bool:
    openai_error = _find_openai_error(exc)
    if openai_error is not None and openai_error is not exc:
        return _is_recoverable_model_error(openai_error)

    if isinstance(
        exc, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
    ):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code in {408, 429} or exc.status_code >= 500
    return False


def _error_code(exc: Exception) -> str:
    openai_error = _find_openai_error(exc)
    if openai_error is not None and openai_error is not exc:
        return _error_code(openai_error)

    if isinstance(exc, openai.RateLimitError):
        return "RATE_LIMITED"
    if isinstance(exc, openai.APITimeoutError):
        return "TIMEOUT"
    if isinstance(exc, openai.APIConnectionError):
        return "SERVICE_UNAVAILABLE"
    if isinstance(exc, openai.AuthenticationError):
        return "UPSTREAM_AUTH_ERROR"
    if isinstance(exc, openai.BadRequestError):
        return "INVALID_REQUEST"
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 408:
            return "TIMEOUT"
        if exc.status_code == 429:
            return "RATE_LIMITED"
        if exc.status_code >= 500:
            return "UPSTREAM_ERROR"
        return "INVALID_REQUEST"
    return "AGENT1_ERROR"


def _find_openai_error(exc: Exception) -> Exception | None:
    if isinstance(exc, openai.OpenAIError):
        return exc

    for nested in (exc.__cause__, exc.__context__):
        if isinstance(nested, Exception):
            found = _find_openai_error(nested)
            if found is not None:
                return found
    return None

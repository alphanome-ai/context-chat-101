import unittest
import asyncio
from collections.abc import AsyncIterator, Generator
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.core.config import Settings
from app.core.chat import ChatService
from app.core.llm.base import BaseChatModel
from app.core.llm.errors import LLMModelError
from app.core.llm.registry import LLMRegistry, ModelDefinition, ProviderDefinition
from app.core.llm.schemas import (
    AssistantMessage,
    ChatCompletionChunk,
    ChatCompletionResponse,
    Choice,
    DeltaContent,
    InferenceRequest,
    StreamChoice,
)
from app.db.models import ChatMessage as StoredChatMessage
from app.db.models import ChatSession, User
from app.db.session import Base, get_db
from app.services.agent0.api.v1 import router as agent0_router
from app.services.agent1.api.v1 import router as agent1_router
from app.services.chat.api.v1 import router as chat_router
from app.services.llm.api.v1 import router as llm_router

USER_ID = "11111111-1111-4111-8111-111111111111"


class FakeChatModel(BaseChatModel):
    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id="fake-completion",
            created=123,
            model=request.model,
            choices=[
                Choice(
                    message=AssistantMessage(content=f"completed:{request.model}"),
                    finish_reason="stop",
                )
            ],
        )

    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        async def _iterator() -> AsyncIterator[ChatCompletionChunk]:
            yield ChatCompletionChunk(
                id="fake-chunk",
                created=123,
                model=request.model,
                choices=[
                    StreamChoice(
                        delta=DeltaContent(
                            role="assistant", content=f"streamed:{request.model}"
                        ),
                        finish_reason=None,
                    )
                ],
            )

        return _iterator()


class StreamErrorChatModel(FakeChatModel):
    def stream(self, request: InferenceRequest) -> AsyncIterator[ChatCompletionChunk]:
        async def _iterator() -> AsyncIterator[ChatCompletionChunk]:
            raise LLMModelError(
                "Upstream streaming failed",
                error_code="UPSTREAM_ERROR",
                status_code=502,
            )
            yield

        return _iterator()


class RecordingChatModel(FakeChatModel):
    last_request: InferenceRequest | None = None

    async def complete(self, request: InferenceRequest) -> ChatCompletionResponse:
        RecordingChatModel.last_request = request
        return await super().complete(request)


def make_test_client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def make_authenticated_chat_client() -> tuple[TestClient, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as db:
        db.add(User(id=USER_ID, email="user@example.com", password_hash="hash"))
        db.commit()

    def override_db() -> Generator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_user() -> User:
        with session_factory() as db:
            user = db.get(User, USER_ID)
            assert user is not None
            db.expunge(user)
            return user

    app = FastAPI()
    app.include_router(chat_router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), session_factory


def make_authenticated_client(router) -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_factory() as db:
        db.add(User(id=USER_ID, email="user@example.com", password_hash="hash"))
        db.commit()

    def override_db() -> Generator[Session]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def override_user() -> User:
        with session_factory() as db:
            user = db.get(User, USER_ID)
            assert user is not None
            db.expunge(user)
            return user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app)


def make_registry() -> LLMRegistry:
    return LLMRegistry(
        (
            ProviderDefinition(
                id="fake",
                name="Fake Provider",
                type="fake",
                default_model="fake-default",
                models=(
                    ModelDefinition(
                        id="fake-default",
                        name="Fake Default",
                        display_name="Fake Default Display",
                        model_cls=FakeChatModel,
                    ),
                    ModelDefinition(
                        id="fake-other",
                        name="Fake Other",
                        display_name="Fake Other Display",
                        model_cls=FakeChatModel,
                    ),
                ),
            ),
        )
    )


def make_recording_registry() -> LLMRegistry:
    return LLMRegistry(
        (
            ProviderDefinition(
                id="fake",
                name="Fake Provider",
                type="fake",
                default_model="recording",
                models=(ModelDefinition(id="recording", model_cls=RecordingChatModel),),
            ),
        )
    )


class LLMApiTests(unittest.TestCase):
    def test_providers_endpoint_lists_registry_models(self) -> None:
        client = make_test_client(llm_router)

        with patch(
            "app.services.llm.api.v1.get_llm_registry", return_value=make_registry()
        ):
            response = client.get("/providers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "providers": [
                    {
                        "id": "fake",
                        "name": "Fake Provider",
                        "type": "fake",
                        "models": [
                            {
                                "id": "fake-default",
                                "name": "Fake Default Display",
                                "displayName": "Fake Default Display",
                                "isDefault": True,
                            },
                            {
                                "id": "fake-other",
                                "name": "Fake Other Display",
                                "displayName": "Fake Other Display",
                                "isDefault": False,
                            },
                        ],
                    }
                ]
            },
        )

    def test_non_streaming_completion_returns_fake_model_response(self) -> None:
        client, _ = make_authenticated_chat_client()

        with patch(
            "app.core.chat.service.get_llm_registry", return_value=make_registry()
        ):
            response = client.post(
                "/run",
                json={
                    "model": "default",
                    "message": "hello",
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "fake-completion")
        self.assertEqual(response.json()["model"], "fake-default")
        self.assertEqual(
            response.json()["choices"][0]["message"]["content"],
            "completed:fake-default",
        )

    def test_unknown_model_returns_structured_error(self) -> None:
        client, _ = make_authenticated_chat_client()

        with patch(
            "app.core.chat.service.get_llm_registry", return_value=make_registry()
        ):
            response = client.post(
                "/run",
                json={
                    "model": "missing-model",
                    "message": "hello",
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_MODEL")
        self.assertEqual(
            response.json()["error"]["message"], "Unsupported model: missing-model"
        )

    def test_streaming_completion_wraps_chunks_as_sse(self) -> None:
        client, _ = make_authenticated_chat_client()

        with patch(
            "app.core.chat.service.get_llm_registry", return_value=make_registry()
        ):
            with client.stream(
                "POST",
                "/run",
                json={
                    "model": "fake-other",
                    "message": "hello",
                    "stream": True,
                },
            ) as response:
                body = response.read().decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("data: ", body)
        self.assertIn('"model":"fake-other"', body)
        self.assertIn('"content":"streamed:fake-other"', body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))

    def test_streaming_completion_wraps_stream_errors_as_sse(self) -> None:
        registry = LLMRegistry(
            (
                ProviderDefinition(
                    id="fake",
                    name="Fake Provider",
                    type="fake",
                    default_model="fake-error",
                    models=(
                        ModelDefinition(
                            id="fake-error", model_cls=StreamErrorChatModel
                        ),
                    ),
                ),
            )
        )

        client, _ = make_authenticated_chat_client()

        with patch("app.core.chat.service.get_llm_registry", return_value=registry):
            with client.stream(
                "POST",
                "/run",
                json={
                    "model": "fake-error",
                    "message": "hello",
                    "stream": True,
                },
            ) as response:
                body = response.read().decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('"error":', body)
        self.assertIn('"message":"Upstream streaming failed"', body)
        self.assertIn('"code":"UPSTREAM_ERROR"', body)
        self.assertTrue(body.endswith("data: [DONE]\n\n"))

    def test_chat_service_resolves_model_before_delegating_to_adapter(self) -> None:
        response = asyncio.run(
            ChatService(make_registry()).run_inference(
                InferenceRequest(
                    model="default",
                    messages=[{"role": "user", "content": "hello"}],
                    stream=False,
                )
            )
        )

        self.assertIsInstance(response, ChatCompletionResponse)
        self.assertEqual(response.model, "fake-default")

    def test_chat_context_manager_builds_prompt_from_saved_session(self) -> None:
        RecordingChatModel.last_request = None
        client, session_factory = make_authenticated_chat_client()
        with session_factory() as db:
            chat_session = ChatSession(
                user_id=USER_ID, title="Saved chat", model="recording"
            )
            db.add(chat_session)
            db.flush()
            db.add_all(
                [
                    StoredChatMessage(
                        session_id=chat_session.id,
                        role="user",
                        content="first user",
                        position=0,
                    ),
                    StoredChatMessage(
                        session_id=chat_session.id,
                        role="assistant",
                        content="first assistant",
                        position=1,
                    ),
                ]
            )
            db.commit()
            session_id = chat_session.id

        with patch(
            "app.core.chat.service.get_llm_registry",
            return_value=make_recording_registry(),
        ):
            response = client.post(
                "/run",
                json={
                    "session_id": session_id,
                    "model": "recording",
                    "message": "second user",
                    "stream": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(RecordingChatModel.last_request)
        assert RecordingChatModel.last_request is not None
        self.assertEqual(
            [
                message.model_dump(exclude_none=True)
                for message in RecordingChatModel.last_request.messages
            ],
            [
                {"role": "user", "content": "first user"},
                {"role": "assistant", "content": "first assistant"},
                {"role": "user", "content": "second user"},
            ],
        )

    def test_agent0_run_returns_missing_configuration_error(self) -> None:
        client = make_authenticated_client(agent0_router)

        with patch(
            "app.core.agent0.service.get_settings",
            return_value=Settings(
                agent0_llm_api_key="",
                agent0_model="",
                agent0_recovery_llm_api_key="",
                agent0_recovery_model="",
                tavily_api_key="",
                mem0_api_key="",
            ),
        ):
            response = client.post(
                "/run",
                json={
                    "message": "hello",
                    "model": "ignored-model",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "AGENT0_CONFIGURATION_ERROR")
        self.assertIn("AGENT0_LLM_API_KEY", response.json()["error"]["message"])

    def test_agent1_run_returns_missing_configuration_error(self) -> None:
        client = make_authenticated_client(agent1_router)

        with patch(
            "app.core.agent1.service.get_settings",
            return_value=Settings(
                agent1_llm_api_key="",
                agent1_model="",
                agent1_recovery_llm_api_key="",
                agent1_recovery_model="",
                tavily_api_key="",
                supermemory_api_key="",
            ),
        ):
            response = client.post(
                "/run",
                json={
                    "message": "hello",
                    "model": "ignored-model",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "AGENT1_CONFIGURATION_ERROR")
        self.assertIn("AGENT1_LLM_API_KEY", response.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
